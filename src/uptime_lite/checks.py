from __future__ import annotations

import http.client
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from uptime_lite import __version__
from uptime_lite.config import CheckConfig

# Returns the HTTP status code. Raises OSError (or http.client.HTTPException) when
# no response could be obtained, including timeouts.
HttpTransport = Callable[[str, float], int]
# Opens and closes a TCP connection. Raises OSError on failure.
TcpTransport = Callable[[str, int, float], None]


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    ok: bool
    at: datetime
    latency_ms: float | None = None
    status_code: int | None = None
    error: str | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def default_http_transport(url: str, timeout: float) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": f"uptime-lite/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        # A 4xx/5xx is still an answer; whether it is acceptable is decided by the caller.
        exc.close()
        return exc.code


def default_tcp_transport(host: str, port: int, timeout: float) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        pass


def status_is_ok(status: int, expected: tuple[int, ...] | None) -> bool:
    if expected is None:
        return 200 <= status < 300
    return status in expected


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
        return "timeout"
    return f"{type(exc).__name__}: {exc}"


def run_http_check(
    check: CheckConfig,
    transport: HttpTransport = default_http_transport,
    clock: Callable[[], datetime] = utc_now,
    timer: Callable[[], float] = time.monotonic,
) -> CheckResult:
    at = clock()
    start = timer()
    try:
        status = transport(check.target, check.timeout)
    # ValueError covers hostnames the stdlib refuses to encode (e.g. a label over 63 chars).
    except (OSError, http.client.HTTPException, ValueError) as exc:
        return CheckResult(check.name, False, at, error=describe_error(exc))
    latency = (timer() - start) * 1000
    if status_is_ok(status, check.expected_status):
        return CheckResult(check.name, True, at, latency_ms=latency, status_code=status)
    return CheckResult(
        check.name,
        False,
        at,
        latency_ms=latency,
        status_code=status,
        error=f"unexpected status {status}",
    )


def run_tcp_check(
    check: CheckConfig,
    transport: TcpTransport = default_tcp_transport,
    clock: Callable[[], datetime] = utc_now,
    timer: Callable[[], float] = time.monotonic,
) -> CheckResult:
    at = clock()
    host, port = check.host_port
    start = timer()
    try:
        transport(host, port, check.timeout)
    except (OSError, ValueError) as exc:
        return CheckResult(check.name, False, at, error=describe_error(exc))
    return CheckResult(check.name, True, at, latency_ms=(timer() - start) * 1000)


def run_check(
    check: CheckConfig,
    http: HttpTransport = default_http_transport,
    tcp: TcpTransport = default_tcp_transport,
    clock: Callable[[], datetime] = utc_now,
    timer: Callable[[], float] = time.monotonic,
) -> CheckResult:
    if check.type == "http":
        return run_http_check(check, http, clock, timer)
    return run_tcp_check(check, tcp, clock, timer)
