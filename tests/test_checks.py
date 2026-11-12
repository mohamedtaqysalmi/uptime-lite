from __future__ import annotations

import http.client
import http.server
import socket
import threading
import urllib.error
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from uptime_lite.checks import (
    default_http_transport,
    default_tcp_transport,
    describe_error,
    run_check,
    run_http_check,
    run_tcp_check,
    status_is_ok,
    utc_now,
)
from uptime_lite.config import CheckConfig

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def clock() -> datetime:
    return NOW


class Timer:
    """Advances 0.25 s per call so latency is deterministic."""

    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        self.value += 0.25
        return self.value


def http_check(**overrides: object) -> CheckConfig:
    fields: dict[str, object] = {
        "name": "web",
        "type": "http",
        "target": "https://example.com/health",
        "interval": 60,
        "timeout": 5.0,
        "failure_threshold": 3,
        "recovery_threshold": 2,
        "expected_status": None,
    }
    fields.update(overrides)
    return CheckConfig(**fields)  # type: ignore[arg-type]


def tcp_check() -> CheckConfig:
    return http_check(name="db", type="tcp", target="192.0.2.10:5432")


def test_http_success_records_status_and_latency() -> None:
    seen: list[tuple[str, float]] = []

    def transport(url: str, timeout: float) -> int:
        seen.append((url, timeout))
        return 200

    result = run_http_check(http_check(), transport, clock, Timer())
    assert result.ok
    assert result.status_code == 200
    assert result.latency_ms == pytest.approx(250)
    assert result.at == NOW
    assert result.error is None
    assert seen == [("https://example.com/health", 5.0)]


@pytest.mark.parametrize(
    ("status", "ok"), [(200, True), (204, True), (301, False), (404, False), (503, False)]
)
def test_default_expected_status_is_any_2xx(status: int, ok: bool) -> None:
    result = run_http_check(http_check(), lambda *_: status, clock, Timer())
    assert result.ok is ok
    assert result.status_code == status


def test_unexpected_status_has_an_error_message() -> None:
    result = run_http_check(http_check(), lambda *_: 503, clock, Timer())
    assert result.error == "unexpected status 503"
    assert result.latency_ms is not None


def test_explicit_expected_status_replaces_the_default() -> None:
    check = http_check(expected_status=(301, 401))
    assert run_http_check(check, lambda *_: 401, clock, Timer()).ok
    assert not run_http_check(check, lambda *_: 200, clock, Timer()).ok


def test_status_is_ok() -> None:
    assert status_is_ok(299, None)
    assert not status_is_ok(300, None)
    assert status_is_ok(404, (404,))


def test_http_timeout() -> None:
    def transport(url: str, timeout: float) -> int:
        raise TimeoutError("timed out")

    result = run_http_check(http_check(), transport, clock, Timer())
    assert not result.ok
    assert result.error == "timeout"
    assert result.status_code is None
    assert result.latency_ms is None


def test_http_url_error_wrapping_a_timeout_is_a_timeout() -> None:
    def transport(url: str, timeout: float) -> int:
        raise urllib.error.URLError(TimeoutError("timed out"))

    assert run_http_check(http_check(), transport, clock, Timer()).error == "timeout"


@pytest.mark.parametrize(
    "exc",
    [ConnectionRefusedError("refused"), http.client.BadStatusLine("junk"), OSError("unreachable")],
)
def test_http_transport_errors_become_failed_results(exc: Exception) -> None:
    def transport(url: str, timeout: float) -> int:
        raise exc

    result = run_http_check(http_check(), transport, clock, Timer())
    assert not result.ok
    assert result.error is not None
    assert type(exc).__name__ in result.error


def test_http_does_not_swallow_programming_errors() -> None:
    def transport(url: str, timeout: float) -> int:
        raise KeyError("bug")

    with pytest.raises(KeyError):
        run_http_check(http_check(), transport, clock, Timer())


def test_tcp_success() -> None:
    seen: list[tuple[str, int, float]] = []

    def transport(host: str, port: int, timeout: float) -> None:
        seen.append((host, port, timeout))

    result = run_tcp_check(tcp_check(), transport, clock, Timer())
    assert result.ok
    assert result.latency_ms == pytest.approx(250)
    assert result.status_code is None
    assert seen == [("192.0.2.10", 5432, 5.0)]


def test_tcp_failure_and_timeout() -> None:
    def refuse(host: str, port: int, timeout: float) -> None:
        raise ConnectionRefusedError("refused")

    def slow(host: str, port: int, timeout: float) -> None:
        raise TimeoutError("timed out")

    refused = run_tcp_check(tcp_check(), refuse, clock, Timer())
    assert not refused.ok
    assert refused.error is not None
    assert refused.error.startswith("ConnectionRefusedError")
    assert run_tcp_check(tcp_check(), slow, clock, Timer()).error == "timeout"


def test_run_check_dispatches_on_type() -> None:
    calls: list[str] = []

    def http(url: str, timeout: float) -> int:
        calls.append("http")
        return 200

    def tcp(host: str, port: int, timeout: float) -> None:
        calls.append("tcp")

    assert run_check(http_check(), http, tcp, clock, Timer()).ok
    assert run_check(tcp_check(), http, tcp, clock, Timer()).ok
    assert calls == ["http", "tcp"]


def test_describe_error_includes_type_and_message() -> None:
    assert describe_error(ConnectionResetError("reset")) == "ConnectionResetError: reset"


def test_utc_now_is_timezone_aware() -> None:
    assert utc_now().tzinfo is not None


# The default transports talk to a throwaway server on the loopback interface.


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status = 200 if self.path == "/ok" else 503
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[http.server.HTTPServer]:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def test_default_http_transport_returns_status_codes(server: http.server.HTTPServer) -> None:
    base = f"http://127.0.0.1:{server.server_port}"
    assert default_http_transport(f"{base}/ok", 5) == 200
    assert default_http_transport(f"{base}/broken", 5) == 503


def test_default_tcp_transport_connects_and_refuses(server: http.server.HTTPServer) -> None:
    default_tcp_transport("127.0.0.1", server.server_port, 5)
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(OSError, match=r"."):
        default_tcp_transport("127.0.0.1", port, 2)


@pytest.mark.parametrize(
    ("kind", "target"),
    [("tcp", "a" * 70 + ".example.com:80"), ("http", "http://a..b/"), ("tcp", "a..b:80")],
)
def test_hostnames_the_stdlib_cannot_encode_fail_the_check_instead_of_raising(
    kind: str, target: str
) -> None:
    result = run_check(http_check(name="x", type=kind, target=target))
    assert not result.ok
    assert result.error is not None
