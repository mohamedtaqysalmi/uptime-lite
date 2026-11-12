from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml

from uptime_lite.alerts import AlertsConfig, TelegramConfig, WebhookConfig

CheckType = Literal["http", "tcp"]

DEFAULT_INTERVAL = 60
DEFAULT_TIMEOUT = 10.0
DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_RECOVERY_THRESHOLD = 2
DEFAULT_STATUS_TITLE = "Status"

_CHECK_KEYS = {
    "name",
    "type",
    "target",
    "interval",
    "timeout",
    "failure_threshold",
    "recovery_threshold",
    "expected_status",
}

_TOP_LEVEL_KEYS = {"checks", "alerts", "status_page"}


class ConfigError(Exception):
    """Raised with every problem found, so one run shows all of them."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("invalid configuration:\n" + "\n".join(f"  - {e}" for e in errors))


@dataclass(frozen=True)
class CheckConfig:
    name: str
    type: CheckType
    target: str
    interval: int
    timeout: float
    failure_threshold: int
    recovery_threshold: int
    # None means any 2xx counts as success. Only used by http checks.
    expected_status: tuple[int, ...] | None = None

    @property
    def host_port(self) -> tuple[str, int]:
        return split_host_port(self.target)


@dataclass(frozen=True)
class StatusPageConfig:
    title: str = DEFAULT_STATUS_TITLE


@dataclass(frozen=True)
class Config:
    checks: tuple[CheckConfig, ...]
    alerts: AlertsConfig | None = None
    status_page: StatusPageConfig | None = None


def split_host_port(target: str) -> tuple[str, int]:
    host, sep, port_text = target.rpartition(":")
    if not sep or not host or not port_text.isdigit():
        raise ValueError("expected host:port")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host:
        raise ValueError("expected host:port")
    return host, port


def load_config(path: str | Path) -> Config:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError([f"cannot read {path}: {exc.strerror or exc}"]) from exc
    return parse_config(text)


def parse_config(text: str) -> Config:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError([f"not valid YAML: {exc}"]) from exc
    return validate_config(data)


def validate_config(data: Any) -> Config:
    if not isinstance(data, dict):
        raise ConfigError(["top level must be a mapping with a 'checks' list"])
    errors: list[str] = []
    for key in data:
        if key not in _TOP_LEVEL_KEYS:
            errors.append(f"unknown top-level key {key!r}")
    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        errors.append("'checks' must be a non-empty list")
        raise ConfigError(errors)

    checks: list[CheckConfig] = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(raw_checks):
        check = _validate_check(index, raw, errors)
        if check is None:
            continue
        if check.name in seen:
            errors.append(
                f"check {check.name!r} (checks[{index}]): field 'name': "
                f"already used by checks[{seen[check.name]}]"
            )
        else:
            seen[check.name] = index
        checks.append(check)

    alerts = _validate_alerts(data.get("alerts"), errors) if "alerts" in data else None
    status_page = (
        _validate_status_page(data.get("status_page"), errors) if "status_page" in data else None
    )

    if errors:
        raise ConfigError(errors)
    return Config(checks=tuple(checks), alerts=alerts, status_page=status_page)


def _label(index: int, raw: Any) -> str:
    name = raw.get("name") if isinstance(raw, dict) else None
    if isinstance(name, str) and name.strip():
        return f"check {name!r} (checks[{index}])"
    return f"checks[{index}]"


def _validate_check(index: int, raw: Any, errors: list[str]) -> CheckConfig | None:
    label = _label(index, raw)
    if not isinstance(raw, dict):
        errors.append(f"{label}: must be a mapping")
        return None

    problems: list[str] = []

    def problem(field: str, message: str) -> None:
        problems.append(f"{label}: field {field!r}: {message}")

    for key in raw:
        if key not in _CHECK_KEYS:
            problem(str(key), "unknown field")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        problem("name", "required, must be a non-empty string")
        name = ""

    check_type = raw.get("type")
    if check_type not in ("http", "tcp"):
        problem("type", "required, must be 'http' or 'tcp'")

    target = raw.get("target")
    if not isinstance(target, str) or not target.strip():
        problem("target", "required, must be a non-empty string")
    elif check_type == "http":
        parts = urlsplit(target)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            problem("target", f"must be an http:// or https:// URL, got {target!r}")
    elif check_type == "tcp":
        try:
            split_host_port(target)
        except ValueError as exc:
            problem("target", f"{exc}, got {target!r}")

    interval = _positive_int(raw, "interval", DEFAULT_INTERVAL, problem)
    failure_threshold = _positive_int(raw, "failure_threshold", DEFAULT_FAILURE_THRESHOLD, problem)
    recovery_threshold = _positive_int(
        raw, "recovery_threshold", DEFAULT_RECOVERY_THRESHOLD, problem
    )

    timeout = raw.get("timeout", DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
        problem("timeout", f"must be a positive number of seconds, got {timeout!r}")
        timeout = DEFAULT_TIMEOUT
    elif interval is not None and timeout > interval:
        problem("timeout", f"must not exceed interval ({timeout} > {interval})")

    expected_status: tuple[int, ...] | None = None
    if "expected_status" in raw:
        value = raw["expected_status"]
        if check_type == "tcp":
            problem("expected_status", "only applies to http checks")
        elif (
            not isinstance(value, list)
            or not value
            or not all(
                isinstance(s, int) and not isinstance(s, bool) and 100 <= s <= 599 for s in value
            )
        ):
            problem("expected_status", f"must be a non-empty list of HTTP codes, got {value!r}")
        elif any(300 <= s < 400 for s in value):
            problem(
                "expected_status",
                "3xx codes can never match because redirects are followed, got " + repr(value),
            )
        else:
            expected_status = tuple(value)

    if problems:
        errors.extend(problems)
        return None
    assert isinstance(target, str)
    assert interval is not None
    assert failure_threshold is not None
    assert recovery_threshold is not None
    return CheckConfig(
        name=name,
        type="http" if check_type == "http" else "tcp",
        target=target,
        interval=interval,
        timeout=float(timeout),
        failure_threshold=failure_threshold,
        recovery_threshold=recovery_threshold,
        expected_status=expected_status,
    )


def _validate_alerts(raw: Any, errors: list[str]) -> AlertsConfig | None:
    if raw is None:
        return AlertsConfig()
    if not isinstance(raw, dict):
        errors.append("alerts: must be a mapping")
        return None
    for key in raw:
        if key not in ("telegram", "webhook"):
            errors.append(f"alerts: unknown field {key!r}")

    telegram = None
    if "telegram" in raw:
        telegram = _validate_telegram(raw["telegram"], errors)

    webhook = None
    if "webhook" in raw:
        webhook = _validate_webhook(raw["webhook"], errors)

    if telegram is None and webhook is None and ("telegram" in raw or "webhook" in raw):
        return None
    return AlertsConfig(telegram=telegram, webhook=webhook)


def _validate_telegram(raw: Any, errors: list[str]) -> TelegramConfig | None:
    if not isinstance(raw, dict):
        errors.append("alerts.telegram: must be a mapping")
        return None
    if "bot_token" in raw or "token" in raw:
        errors.append(
            "alerts.telegram: do not put the bot token in YAML; set TELEGRAM_BOT_TOKEN instead"
        )
    for key in raw:
        if key not in ("chat_id", "api_base", "bot_token", "token"):
            errors.append(f"alerts.telegram: unknown field {key!r}")
    chat_id = raw.get("chat_id")
    if isinstance(chat_id, int) and not isinstance(chat_id, bool):
        chat_id = str(chat_id)
    if not isinstance(chat_id, str) or not chat_id.strip():
        errors.append("alerts.telegram: field 'chat_id': required, must be a non-empty string")
        return None
    if "bot_token" in raw or "token" in raw:
        return None
    api_base = raw.get("api_base", "https://api.telegram.org")
    if (
        not isinstance(api_base, str)
        or not api_base.startswith("https://")
        or any(c.isspace() for c in api_base)
    ):
        errors.append(f"alerts.telegram: field 'api_base': must be an https URL, got {api_base!r}")
        return None
    return TelegramConfig(chat_id=chat_id.strip(), api_base=api_base.rstrip("/"))


def _validate_webhook(raw: Any, errors: list[str]) -> WebhookConfig | None:
    if not isinstance(raw, dict):
        errors.append("alerts.webhook: must be a mapping")
        return None
    for key in raw:
        if key not in ("url", "require_bearer", "timeout"):
            errors.append(f"alerts.webhook: unknown field {key!r}")
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        errors.append("alerts.webhook: field 'url': required, must be a non-empty string")
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        errors.append(f"alerts.webhook: field 'url': must be an http(s) URL, got {url!r}")
        return None
    require_bearer = raw.get("require_bearer", False)
    if not isinstance(require_bearer, bool):
        errors.append(
            f"alerts.webhook: field 'require_bearer': must be a boolean, got {require_bearer!r}"
        )
        return None
    timeout = raw.get("timeout", 10.0)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
        errors.append(
            f"alerts.webhook: field 'timeout': must be a positive number, got {timeout!r}"
        )
        return None
    return WebhookConfig(url=url.strip(), require_bearer=require_bearer, timeout=float(timeout))


def _validate_status_page(raw: Any, errors: list[str]) -> StatusPageConfig | None:
    if raw is None:
        return StatusPageConfig()
    if not isinstance(raw, dict):
        errors.append("status_page: must be a mapping")
        return None
    for key in raw:
        if key != "title":
            errors.append(f"status_page: unknown field {key!r}")
    title = raw.get("title", DEFAULT_STATUS_TITLE)
    if not isinstance(title, str) or not title.strip():
        errors.append("status_page: field 'title': must be a non-empty string")
        return None
    return StatusPageConfig(title=title.strip())


def _positive_int(raw: dict[str, Any], field: str, default: int, problem: Any) -> int | None:
    value = raw.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        problem(field, f"must be an integer >= 1, got {value!r}")
        return None
    return value
