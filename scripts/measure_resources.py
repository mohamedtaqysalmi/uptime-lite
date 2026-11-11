#!/usr/bin/env python3
"""Measure wall time, CPU time and peak traced memory for 20 fake checks.

Uses injectable transports so nothing leaves the machine. Numbers are written to
stdout as plain text for docs/resource-usage.md.
"""

from __future__ import annotations

import argparse
import statistics
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

from uptime_lite.checks import run_check
from uptime_lite.config import CheckConfig
from uptime_lite.monitor import handle_result
from uptime_lite.storage import Storage


def _checks(count: int) -> list[CheckConfig]:
    out: list[CheckConfig] = []
    for i in range(count):
        if i % 2 == 0:
            out.append(
                CheckConfig(
                    name=f"http-{i}",
                    type="http",
                    target=f"https://example.com/{i}",
                    interval=60,
                    timeout=2.0,
                    failure_threshold=3,
                    recovery_threshold=2,
                )
            )
        else:
            out.append(
                CheckConfig(
                    name=f"tcp-{i}",
                    type="tcp",
                    target=f"127.0.0.1:{18000 + i}",
                    interval=60,
                    timeout=2.0,
                    failure_threshold=3,
                    recovery_threshold=2,
                )
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    checks = _checks(args.count)
    db_path = args.db or Path(":memory:")
    # sqlite needs a real path for file DBs; use a temp path string for memory.
    storage = Storage(":memory:" if args.db is None else db_path)

    def http_ok(url: str, timeout: float) -> int:
        time.sleep(0.001)
        return 200

    def tcp_ok(host: str, port: int, timeout: float) -> None:
        time.sleep(0.001)

    latencies: list[float] = []
    tracemalloc.start()
    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    for check in checks:
        result = run_check(check, http=http_ok, tcp=tcp_ok, clock=lambda: datetime.now(UTC))
        handle_result(storage, check, result)
        if result.latency_ms is not None:
            latencies.append(result.latency_ms)
    wall = time.perf_counter() - wall0
    cpu = time.process_time() - cpu0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    storage.close()

    print(f"checks={args.count}")
    print(f"wall_seconds={wall:.4f}")
    print(f"cpu_seconds={cpu:.4f}")
    print(f"tracemalloc_peak_kib={peak / 1024:.1f}")
    if latencies:
        print(f"latency_ms_mean={statistics.mean(latencies):.2f}")
        print(f"latency_ms_p95={statistics.quantiles(latencies, n=20)[18]:.2f}")
    print(
        "note=fake transports (1ms sleep); measures Python work + SQLite writes, "
        "not real network RTT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
