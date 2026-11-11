from __future__ import annotations

from pathlib import Path

import pytest

from uptime_lite.config import (
    DEFAULT_FAILURE_THRESHOLD,
    DEFAULT_INTERVAL,
    ConfigError,
    load_config,
    parse_config,
    split_host_port,
)

EXAMPLE = Path(__file__).parent.parent / "examples" / "config.example.yaml"


def errors_for(text: str) -> list[str]:
    with pytest.raises(ConfigError) as info:
        parse_config(text)
    return info.value.errors


def test_example_config_loads() -> None:
    config = load_config(EXAMPLE)
    assert [c.name for c in config.checks] == [
        "example-website",
        "example-api-health",
        "example-database",
        "example-ssh",
    ]
    assert config.checks[2].host_port == ("192.0.2.10", 5432)
    assert config.checks[0].expected_status == (200,)


def test_defaults_are_applied() -> None:
    config = parse_config("checks:\n  - {name: a, type: http, target: 'https://example.com'}\n")
    check = config.checks[0]
    assert check.interval == DEFAULT_INTERVAL
    assert check.failure_threshold == DEFAULT_FAILURE_THRESHOLD
    assert check.expected_status is None


def test_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")


def test_invalid_yaml() -> None:
    assert "not valid YAML" in errors_for("checks: [unclosed")[0]


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just a string"])
def test_top_level_must_be_a_mapping(text: str) -> None:
    assert "top level must be a mapping" in errors_for(text)[0]


def test_unknown_top_level_key() -> None:
    errors = errors_for("chekcs: []\nchecks: [{name: a, type: tcp, target: 'h:1'}]\n")
    assert errors == ["unknown top-level key 'chekcs'"]


def test_alerts_and_status_page_parse() -> None:
    config = parse_config(
        """
checks:
  - {name: a, type: http, target: 'https://example.com'}
alerts:
  telegram:
    chat_id: "99"
  webhook:
    url: https://hooks.example.com/h
    require_bearer: true
status_page:
  title: Ops Board
"""
    )
    assert config.alerts is not None
    assert config.alerts.telegram is not None
    assert config.alerts.telegram.chat_id == "99"
    assert config.alerts.webhook is not None
    assert config.alerts.webhook.require_bearer is True
    assert config.status_page is not None
    assert config.status_page.title == "Ops Board"


def test_telegram_token_rejected_in_yaml() -> None:
    errors = errors_for(
        """
checks:
  - {name: a, type: http, target: 'https://example.com'}
alerts:
  telegram:
    chat_id: "1"
    bot_token: secret
"""
    )
    assert any("TELEGRAM_BOT_TOKEN" in e for e in errors)


@pytest.mark.parametrize("text", ["checks: []\n", "checks: {}\n", "other: 1\n"])
def test_checks_must_be_non_empty_list(text: str) -> None:
    assert any("non-empty list" in e for e in errors_for(text))


def test_check_must_be_a_mapping() -> None:
    assert errors_for("checks:\n  - just-a-string\n") == ["checks[0]: must be a mapping"]


def test_errors_name_the_check_and_field() -> None:
    errors = errors_for(
        """
checks:
  - name: web
    type: http
    target: https://example.com
    interval: 0
  - name: db
    type: tcp
    target: not-a-target
    failure_threshold: many
"""
    )
    assert any("check 'web' (checks[0]): field 'interval'" in e for e in errors)
    assert any("check 'db' (checks[1]): field 'target'" in e for e in errors)
    assert any("check 'db' (checks[1]): field 'failure_threshold'" in e for e in errors)


def test_all_problems_are_reported_together() -> None:
    errors = errors_for("checks:\n  - {type: ftp}\n  - {name: b}\n")
    assert any(e.startswith("checks[0]: field 'name'") for e in errors)
    assert any(e.startswith("checks[0]: field 'type'") for e in errors)
    assert any(e.startswith("checks[0]: field 'target'") for e in errors)
    assert any("check 'b' (checks[1]): field 'type'" in e for e in errors)


def test_error_message_lists_every_error() -> None:
    with pytest.raises(ConfigError) as info:
        parse_config("checks:\n  - {name: b}\n")
    assert str(info.value).startswith("invalid configuration:")
    assert "check 'b'" in str(info.value)


def test_unknown_field_is_rejected() -> None:
    errors = errors_for("checks:\n  - {name: a, type: tcp, target: 'h:1', intervall: 5}\n")
    assert errors == ["check 'a' (checks[0]): field 'intervall': unknown field"]


def test_duplicate_names() -> None:
    errors = errors_for(
        "checks:\n"
        "  - {name: a, type: tcp, target: 'h:1'}\n"
        "  - {name: a, type: tcp, target: 'h:2'}\n"
    )
    assert errors == ["check 'a' (checks[1]): field 'name': already used by checks[0]"]


@pytest.mark.parametrize("target", ["example.com", "ftp://example.com", "https://", "  "])
def test_bad_http_targets(target: str) -> None:
    errors = errors_for(f"checks:\n  - {{name: a, type: http, target: '{target}'}}\n")
    assert "field 'target'" in errors[0]


@pytest.mark.parametrize("target", ["host", "host:", ":80", "host:abc", "host:0", "host:70000"])
def test_bad_tcp_targets(target: str) -> None:
    errors = errors_for(f"checks:\n  - {{name: a, type: tcp, target: '{target}'}}\n")
    assert "field 'target'" in errors[0]


@pytest.mark.parametrize("field", ["interval", "failure_threshold", "recovery_threshold"])
@pytest.mark.parametrize("value", ["0", "-1", "1.5", "'5'", "true", "null"])
def test_integer_fields_reject_bad_values(field: str, value: str) -> None:
    errors = errors_for(f"checks:\n  - {{name: a, type: tcp, target: 'h:1', {field}: {value}}}\n")
    assert f"field '{field}'" in errors[0]


@pytest.mark.parametrize("value", ["0", "-2", "'3'", "true"])
def test_timeout_rejects_bad_values(value: str) -> None:
    errors = errors_for(f"checks:\n  - {{name: a, type: tcp, target: 'h:1', timeout: {value}}}\n")
    assert "field 'timeout'" in errors[0]


def test_timeout_must_not_exceed_interval() -> None:
    errors = errors_for(
        "checks:\n  - {name: a, type: tcp, target: 'h:1', interval: 5, timeout: 6}\n"
    )
    assert "must not exceed interval" in errors[0]


def test_timeout_may_be_fractional() -> None:
    config = parse_config("checks:\n  - {name: a, type: tcp, target: 'h:1', timeout: 2.5}\n")
    assert config.checks[0].timeout == 2.5


@pytest.mark.parametrize("value", ["[]", "200", "[99]", "[600]", "['200']", "[true]"])
def test_expected_status_rejects_bad_values(value: str) -> None:
    errors = errors_for(
        f"checks:\n  - {{name: a, type: http, target: 'http://e.com', expected_status: {value}}}\n"
    )
    assert "field 'expected_status'" in errors[0]


def test_expected_status_is_http_only() -> None:
    errors = errors_for(
        "checks:\n  - {name: a, type: tcp, target: 'h:1', expected_status: [200]}\n"
    )
    assert "only applies to http" in errors[0]


@pytest.mark.parametrize(
    ("target", "expected"),
    [("example.com:80", ("example.com", 80)), ("[2001:db8::1]:443", ("2001:db8::1", 443))],
)
def test_split_host_port(target: str, expected: tuple[str, int]) -> None:
    assert split_host_port(target) == expected


def test_split_host_port_rejects_empty_bracketed_host() -> None:
    with pytest.raises(ValueError, match="host:port"):
        split_host_port("[]:80")
