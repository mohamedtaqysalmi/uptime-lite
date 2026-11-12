"""Runs the cases shared with the demo's JavaScript port against the real state machine."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from uptime_lite.incidents import CheckState, evaluate

CASES_FILE = Path(__file__).parent.parent / "site" / "debounce-cases.json"
CASES: list[dict[str, Any]] = json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_case(case: dict[str, Any]) -> None:
    state = CheckState()
    events: list[list[object]] = []
    for index, char in enumerate(case["pattern"]):
        state, transition = evaluate(
            state,
            char == ".",
            T0 + timedelta(seconds=index),
            case["failure_threshold"],
            case["recovery_threshold"],
        )
        if transition is not None:
            events.append([index, transition.kind.value])
    assert events == case["events"]
    assert {
        "status": state.status.value,
        "failures": state.consecutive_failures,
        "successes": state.consecutive_successes,
    } == case["final"]
