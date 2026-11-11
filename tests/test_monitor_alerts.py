from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from uptime_lite.alerts import Alerter, AlertsConfig, WebhookConfig
from uptime_lite.checks import CheckResult
from uptime_lite.config import CheckConfig
from uptime_lite.incidents import TransitionKind
from uptime_lite.monitor import handle_result
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
