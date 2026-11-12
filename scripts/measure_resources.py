#!/usr/bin/env python3
"""Measure one `uptime-lite check` run with 20 real checks against a loopback server.

The parent starts a small HTTP server on 127.0.0.1, writes a config with 10 HTTP and
10 TCP checks pointing at it, and runs the real CLI entry point in a fresh child process
several times. Each child reports its own peak resident memory and CPU time (including interpreter
startup and imports); the parent times the whole process, and the child times the checks.
Loopback means no real network latency is included.

    python scripts/measure_resources.py            # 20 checks, 5 runs
    python scripts/measure_resources.py --runs 10

Peak memory is read from the OS (Windows: PeakWorkingSetSize, Linux/macOS: ru_maxrss).
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        pass


def _peak_rss_kib() -> float:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return counters.PeakWorkingSetSize / 1024
    import resource

    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # ru_maxrss is bytes on macOS and kilobytes on Linux.
    return peak / 1024 if sys.platform == "darwin" else peak


def _child(config: Path, db: Path, baseline: bool) -> None:
    wall0 = time.perf_counter()
    if not baseline:
        from uptime_lite.cli import main

        main(["check", "-c", str(config), "-d", str(db), "--no-alerts"])
    stats = {
        "peak_rss_kib": _peak_rss_kib(),
        "cpu_s": time.process_time(),
        "wall_s": time.perf_counter() - wall0,
    }
    print("STATS " + json.dumps(stats))


def _write_config(path: Path, port: int, count: int) -> None:
    lines = ["checks:"]
    for i in range(count):
        if i % 2 == 0:
            target = f"http://127.0.0.1:{port}/{i}"
            kind = "http"
        else:
            target = f"127.0.0.1:{port}"
            kind = "tcp"
        lines += [
            f"  - name: {kind}-{i}",
            f"    type: {kind}",
            f"    target: {target}",
            "    interval: 60",
            "    timeout: 5",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_child(config: Path, db: Path, *, baseline: bool) -> dict[str, float]:
    argv = [sys.executable, __file__, "--child", str(config), str(db)]
    if baseline:
        argv.append("--baseline")
    start = time.perf_counter()
    done = subprocess.run(argv, capture_output=True, text=True, check=True)
    total = time.perf_counter() - start
    for line in done.stdout.splitlines():
        if line.startswith("STATS "):
            parsed: dict[str, float] = json.loads(line[6:])
            parsed["process_wall_s"] = total
            return parsed
    raise RuntimeError(f"child printed no stats:\n{done.stdout}\n{done.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--child", nargs=2, metavar=("CONFIG", "DB"))
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()

    if args.child:
        _child(Path(args.child[0]), Path(args.child[1]), args.baseline)
        return 0

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yaml"
            _write_config(config, server.server_port, args.count)
            baseline = [_run_child(config, Path(tmp) / "base.db", baseline=True)]
            runs = [
                _run_child(config, Path(tmp) / f"run{i}.db", baseline=False)
                for i in range(args.runs)
            ]
    finally:
        server.shutdown()

    def column(rows: list[dict[str, float]], key: str) -> list[float]:
        return [row[key] for row in rows]

    print(f"python={platform.python_version()} platform={platform.platform()}")
    print(f"checks={args.count} runs={args.runs} (loopback server, fresh process per run)")
    print(f"idle_interpreter_peak_rss_mib={baseline[0]['peak_rss_kib'] / 1024:.1f}")
    print(f"idle_interpreter_cpu_seconds={baseline[0]['cpu_s']:.3f}")
    for key, label, scale in (
        ("peak_rss_kib", "peak_rss_mib", 1024),
        ("cpu_s", "cpu_seconds", 1),
        ("wall_s", "check_wall_seconds", 1),
        ("process_wall_s", "process_wall_seconds", 1),
    ):
        values = [v / scale for v in column(runs, key)]
        print(
            f"{label}: median={statistics.median(values):.3f} "
            f"min={min(values):.3f} max={max(values):.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
