from __future__ import annotations

import http.client
import http.server
import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from uptime_lite.alerts import (
    TELEGRAM_TOKEN_ENV,
    WEBHOOK_BEARER_ENV,
    Alerter,
    AlertsConfig,
    TelegramConfig,
    WebhookConfig,
    default_http_post,
    format_text,
    webhook_payload,
)
from uptime_lite.incidents import Transition, TransitionKind

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 1, 1, 12, 3, 0, tzinfo=UTC)


@pytest.fixture
def opened() -> Transition:
    return Transition(TransitionKind.OPENED, at=T1, started_at=T0)


@pytest.fixture
def resolved() -> Transition:
    return Transition(TransitionKind.RESOLVED, at=T1, started_at=T0)


def test_format_text_opened_and_resolved(opened: Transition, resolved: Transition) -> None:
    assert "DOWN: web" in format_text("web", opened, "timeout")
    assert "timeout" in format_text("web", opened, "timeout")
    assert "UP: web" in format_text("web", resolved, None)
    assert "recovered" in format_text("web", resolved, None)


def test_webhook_payload_shape(opened: Transition) -> None:
    payload = webhook_payload("api", opened, "unexpected status 500")
    assert payload["event"] == "incident.opened"
    assert payload["check"] == "api"
    assert payload["error"] == "unexpected status 500"
    assert payload["at"] == T1.isoformat()


def test_telegram_send_posts_send_message(opened: Transition) -> None:
    calls: list[tuple[str, dict[str, str], bytes, float]] = []

    def post(
        url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        calls.append((url, dict(headers), body, timeout))
        return 200, b'{"ok":true}'

    alerter = Alerter(
        AlertsConfig(telegram=TelegramConfig(chat_id="42")),
        env={TELEGRAM_TOKEN_ENV: "secret-token"},
        post=post,
    )
    alerter.notify("web", opened, "timeout")
    assert len(calls) == 1
    url, headers, body, _ = calls[0]
    assert url.endswith("/botsecret-token/sendMessage")
    assert headers["Content-Type"] == "application/json"
    data = json.loads(body)
    assert data["chat_id"] == "42"
    assert "DOWN: web" in data["text"]


def test_telegram_skipped_without_token(
    opened: Transition, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[object] = []

    def post(*_a: object, **_k: object) -> tuple[int, bytes]:
        calls.append(1)
        return 200, b""

    alerter = Alerter(
        AlertsConfig(telegram=TelegramConfig(chat_id="42")),
        env={},
        post=post,
    )
    with caplog.at_level("ERROR"):
        alerter.notify("web", opened, None)
    assert calls == []
    assert TELEGRAM_TOKEN_ENV in caplog.text


def test_webhook_send_and_bearer(resolved: Transition) -> None:
    calls: list[tuple[str, dict[str, str], bytes]] = []

    def post(
        url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        calls.append((url, dict(headers), body))
        return 204, b""

    alerter = Alerter(
        AlertsConfig(webhook=WebhookConfig(url="https://hooks.example/x", require_bearer=True)),
        env={WEBHOOK_BEARER_ENV: "tok"},
        post=post,
    )
    alerter.notify("db", resolved, None)
    assert len(calls) == 1
    url, headers, body = calls[0]
    assert url == "https://hooks.example/x"
    assert headers["Authorization"] == "Bearer tok"
    data = json.loads(body)
    assert data["event"] == "incident.resolved"
    assert data["check"] == "db"


def test_webhook_bearer_required_but_missing(
    opened: Transition, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[object] = []

    def post(*_a: object, **_k: object) -> tuple[int, bytes]:
        calls.append(1)
        return 200, b""

    alerter = Alerter(
        AlertsConfig(webhook=WebhookConfig(url="https://hooks.example/x", require_bearer=True)),
        env={},
        post=post,
    )
    with caplog.at_level("ERROR"):
        alerter.notify("web", opened, None)
    assert calls == []
    assert WEBHOOK_BEARER_ENV in caplog.text


def test_http_error_is_logged_not_raised(
    opened: Transition, caplog: pytest.LogCaptureFixture
) -> None:
    def post(*_a: object, **_k: object) -> tuple[int, bytes]:
        return 500, b"nope"

    alerter = Alerter(
        AlertsConfig(webhook=WebhookConfig(url="https://hooks.example/x")),
        env={},
        post=post,
    )
    with caplog.at_level("ERROR"):
        alerter.notify("web", opened, "x")
    assert "HTTP 500" in caplog.text


def test_os_error_is_logged(opened: Transition, caplog: pytest.LogCaptureFixture) -> None:
    def post(*_a: object, **_k: object) -> tuple[int, bytes]:
        raise TimeoutError("slow")

    alerter = Alerter(
        AlertsConfig(telegram=TelegramConfig(chat_id="1")),
        env={TELEGRAM_TOKEN_ENV: "t"},
        post=post,
    )
    with caplog.at_level("ERROR"):
        alerter.notify("web", opened, None)
    assert "telegram alert failed" in caplog.text


def test_failure_message_never_reaches_the_log_or_the_caller(
    opened: Transition, caplog: pytest.LogCaptureFixture
) -> None:
    # urllib puts the request path, and so the bot token, in some exception messages.
    def post(
        url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        raise http.client.InvalidURL(f"URL can't contain control characters. {url!r}")

    alerter = Alerter(
        AlertsConfig(telegram=TelegramConfig(chat_id="42")),
        env={TELEGRAM_TOKEN_ENV: "123456:SECRET-TOKEN"},
        post=post,
    )
    alerter.notify("web", opened, "timeout")
    assert "SECRET-TOKEN" not in caplog.text
    assert "InvalidURL" in caplog.text


@pytest.mark.parametrize("exc", [ValueError("bad"), http.client.IncompleteRead(b"")])
def test_unexpected_transport_errors_do_not_skip_the_other_channel(
    opened: Transition, exc: Exception
) -> None:
    bodies: list[str] = []

    def post(
        url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        if "telegram" in url:
            raise exc
        bodies.append(url)
        return 200, b"ok"

    alerter = Alerter(
        AlertsConfig(
            telegram=TelegramConfig(chat_id="42"),
            webhook=WebhookConfig(url="https://hooks.example/h"),
        ),
        env={TELEGRAM_TOKEN_ENV: "t"},
        post=post,
    )
    alerter.notify("web", opened, None)
    assert bodies == ["https://hooks.example/h"]


def test_alert_times_are_utc(opened: Transition) -> None:
    assert "12:03:00 UTC" in format_text("web", opened, "timeout")


def test_default_http_post_returns_status_and_body_even_for_errors() -> None:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            body = self.rfile.read(length)
            status = 200 if self.path == "/ok" else 500
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        assert default_http_post(f"{base}/ok", {}, b"hello", 5) == (200, b"hello")
        assert default_http_post(f"{base}/fail", {}, b"hello", 5) == (500, b"hello")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
