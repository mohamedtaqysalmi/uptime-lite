"""Telegram and webhook alerts. Transports are injectable; no secrets are logged."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from uptime_lite.incidents import Transition, TransitionKind

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
WEBHOOK_BEARER_ENV = "WEBHOOK_BEARER_TOKEN"

# POST url with headers and body; returns (status_code, response_body).
HttpPoster = Callable[[str, Mapping[str, str], bytes, float], tuple[int, bytes]]


@dataclass(frozen=True)
class TelegramConfig:
    chat_id: str
    # Token is read from TELEGRAM_BOT_TOKEN at send time, never stored here.
    api_base: str = "https://api.telegram.org"


@dataclass(frozen=True)
class WebhookConfig:
    url: str
    # If True, Authorization: Bearer $WEBHOOK_BEARER_TOKEN is required at send time.
    require_bearer: bool = False
    timeout: float = 10.0


@dataclass(frozen=True)
class AlertsConfig:
    telegram: TelegramConfig | None = None
    webhook: WebhookConfig | None = None


def default_http_post(
    url: str, headers: Mapping[str, str], body: bytes, timeout: float
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        exc.close()
        return exc.code, payload


def format_text(check_name: str, transition: Transition, error: str | None) -> str:
    started = _fmt(transition.started_at)
    at = _fmt(transition.at)
    if transition.kind is TransitionKind.OPENED:
        detail = error or "check failed"
        return f"DOWN: {check_name} — {detail} (first failure {started}, opened {at})"
    return f"UP: {check_name} — recovered (down from {started} to {at})"


def webhook_payload(
    check_name: str, transition: Transition, error: str | None
) -> dict[str, object]:
    event = "incident.opened" if transition.kind is TransitionKind.OPENED else "incident.resolved"
    return {
        "event": event,
        "check": check_name,
        "at": transition.at.isoformat(),
        "started_at": transition.started_at.isoformat(),
        "error": error,
    }


class Alerter:
    """Sends incident transitions to the configured channels. Failures are logged, not raised."""

    def __init__(
        self,
        config: AlertsConfig,
        *,
        env: Mapping[str, str] | None = None,
        post: HttpPoster = default_http_post,
        timeout: float = 10.0,
    ) -> None:
        self._config = config
        self._env = env if env is not None else os.environ
        self._post = post
        self._timeout = timeout

    def notify(self, check_name: str, transition: Transition, error: str | None = None) -> None:
        text = format_text(check_name, transition, error)
        if self._config.telegram is not None:
            self._send_telegram(self._config.telegram, text)
        if self._config.webhook is not None:
            self._send_webhook(self._config.webhook, webhook_payload(check_name, transition, error))

    def _send_telegram(self, cfg: TelegramConfig, text: str) -> None:
        token = self._env.get(TELEGRAM_TOKEN_ENV, "").strip()
        if not token:
            logger.error("telegram alert skipped: set %s in the environment", TELEGRAM_TOKEN_ENV)
            return
        url = f"{cfg.api_base.rstrip('/')}/bot{token}/sendMessage"
        body = json.dumps({"chat_id": cfg.chat_id, "text": text}).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "uptime-lite"}
        try:
            status, raw = self._post(url, headers, body, self._timeout)
        except Exception as exc:
            # Only the exception type is logged: messages from urllib can contain the URL,
            # and the Telegram URL contains the bot token.
            logger.error("telegram alert failed: %s", type(exc).__name__)
            return
        if status >= 400:
            logger.error("telegram alert rejected with HTTP %s", status)
            logger.debug("telegram response body length=%s", len(raw))

    def _send_webhook(self, cfg: WebhookConfig, payload: dict[str, object]) -> None:
        headers = {"Content-Type": "application/json", "User-Agent": "uptime-lite"}
        if cfg.require_bearer:
            bearer = self._env.get(WEBHOOK_BEARER_ENV, "").strip()
            if not bearer:
                logger.error("webhook alert skipped: set %s in the environment", WEBHOOK_BEARER_ENV)
                return
            headers["Authorization"] = f"Bearer {bearer}"
        body = json.dumps(payload).encode("utf-8")
        try:
            status, raw = self._post(cfg.url, headers, body, cfg.timeout)
        except Exception as exc:
            logger.error("webhook alert failed: %s", type(exc).__name__)
            return
        if status >= 400:
            logger.error("webhook alert rejected with HTTP %s", status)
            logger.debug("webhook response body length=%s", len(raw))


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
