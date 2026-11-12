from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from uptime_lite.alerts import Alerter, AlertsConfig, WebhookConfig
from uptime_lite.checks import CheckResult
from uptime_lite.config import CheckConfig, Config
from uptime_lite.incidents import TransitionKind
from uptime_lite.monitor import handle_result, run_once
from uptime_lite.storage import Storage

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
CHECK = CheckConfig("web", "http", "https://example.com", 60, 5.0, 2, 1)


def test_handle_result_notifies_on_open(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "a.db")
    posts: list[bytes] = []

    def post(
        url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        posts.append(body)
        return 200, b"ok"

    alerter = Alerter(
        AlertsConfig(webhook=WebhookConfig(url="https://hooks.example/h")),
        env={},
        post=post,
    )
    handle_result(storage, CHECK, CheckResult("web", False, T0, error="timeout"), alerter)
    assert posts == []
    transition = handle_result(
        storage,
        CHECK,
        CheckResult("web", False, T0 + timedelta(seconds=30), error="timeout"),
        alerter,
    )
    assert transition is not None
    assert transition.kind is TransitionKind.OPENED
    assert len(posts) == 1
    storage.close()


def test_one_crashing_check_does_not_stop_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = Storage(tmp_path / "r.db")
    good = CheckConfig("good", "http", "https://example.com", 60, 5.0, 2, 1)
    bad = CheckConfig("bad", "http", "https://example.com", 60, 5.0, 2, 1)

    def fake_run_check(check: CheckConfig) -> CheckResult:
        if check.name == "bad":
            raise RuntimeError("boom")
        return CheckResult(check.name, True, T0, latency_ms=1.0, status_code=200)

    monkeypatch.setattr("uptime_lite.monitor.run_check", fake_run_check)
    outcomes = run_once(Config(checks=(bad, good)), storage)
    assert [(c.name, r.ok) for c, r, _ in outcomes] == [("bad", False), ("good", True)]
    assert outcomes[0][1].error == "internal error: RuntimeError"
    assert storage.load_state("good").last_at == T0
    storage.close()
