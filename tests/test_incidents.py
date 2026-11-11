from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta, timezone

import pytest

from uptime_lite.incidents import (
    CheckState,
    IncidentTracker,
    Status,
    TransitionKind,
    evaluate,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(seconds=30)
        return current


def make(failures: int = 3, recoveries: int = 2) -> tuple[IncidentTracker, FakeClock]:
    clock = FakeClock()
    return IncidentTracker(failures, recoveries, clock), clock


def status(tracker: IncidentTracker) -> Status:
    return tracker.state.status


def feed(tracker: IncidentTracker, pattern: str) -> list[str]:
    """'.' is a success and 'x' a failure. Returns the transitions as 'opened'/'resolved'."""
    events = []
    for char in pattern:
        transition = tracker.record(char == ".")
        if transition is not None:
            events.append(transition.kind.value)
    return events


def test_starts_up_with_no_history() -> None:
    tracker, _ = make()
    assert status(tracker) is Status.UP
    assert tracker.state.consecutive_failures == 0


def test_opens_on_exactly_the_nth_consecutive_failure() -> None:
    tracker, _ = make(failures=3)
    assert tracker.record(False) is None
    assert tracker.record(False) is None
    assert status(tracker) is Status.UP
    transition = tracker.record(False)
    assert transition is not None
    assert transition.kind is TransitionKind.OPENED
    assert status(tracker) is Status.DOWN


def test_one_failure_below_threshold_never_opens() -> None:
    tracker, _ = make(failures=3)
    assert feed(tracker, "xx") == []
    assert status(tracker) is Status.UP


def test_threshold_of_one_opens_immediately() -> None:
    tracker, _ = make(failures=1, recoveries=1)
    assert feed(tracker, "x.") == ["opened", "resolved"]


def test_incident_start_is_first_failure_and_open_time_is_deciding_result() -> None:
    tracker, clock = make(failures=3)
    tracker.record(True)
    tracker.record(False)  # T0 + 30s
    tracker.record(False)
    transition = tracker.record(False)  # T0 + 90s
    assert transition is not None
    assert transition.started_at == T0 + timedelta(seconds=30)
    assert transition.at == T0 + timedelta(seconds=90)
    assert clock.now == T0 + timedelta(seconds=120)


def test_stays_down_without_repeating_the_alert() -> None:
    tracker, _ = make(failures=2)
    assert feed(tracker, "xxxxxxxx") == ["opened"]


def test_resolves_only_after_m_consecutive_successes() -> None:
    tracker, _ = make(failures=2, recoveries=3)
    assert feed(tracker, "xx") == ["opened"]
    assert feed(tracker, "..") == []
    assert status(tracker) is Status.DOWN
    assert feed(tracker, ".") == ["resolved"]
    assert status(tracker) is Status.UP


def test_resolution_reports_incident_start_and_resolve_time() -> None:
    tracker, _ = make(failures=2, recoveries=2)
    feed(tracker, "xx")
    tracker.record(True)
    transition = tracker.record(True)
    assert transition is not None
    assert transition.kind is TransitionKind.RESOLVED
    assert transition.started_at == T0
    assert transition.at == T0 + timedelta(seconds=90)


def test_flapping_below_the_failure_threshold_never_alerts() -> None:
    tracker, _ = make(failures=3, recoveries=2)
    assert feed(tracker, "xx.xx.xx.xx.xx.") == []
    assert status(tracker) is Status.UP


def test_flapping_while_down_does_not_resolve_or_reopen() -> None:
    tracker, _ = make(failures=3, recoveries=3)
    assert feed(tracker, "xxx") == ["opened"]
    assert feed(tracker, ".x.x..x.x..x") == []
    assert status(tracker) is Status.DOWN
    assert tracker.state.incident_started_at == T0


def test_failure_resets_the_recovery_streak() -> None:
    tracker, _ = make(failures=1, recoveries=3)
    feed(tracker, "x..")
    assert tracker.state.consecutive_successes == 2
    feed(tracker, "x")
    assert tracker.state.consecutive_successes == 0
    assert feed(tracker, "..") == []
    assert feed(tracker, ".") == ["resolved"]


def test_success_resets_the_failure_streak() -> None:
    tracker, _ = make(failures=3)
    feed(tracker, "xx.")
    assert tracker.state.consecutive_failures == 0
    assert feed(tracker, "xx") == []
    assert feed(tracker, "x") == ["opened"]


def test_second_incident_after_recovery() -> None:
    tracker, _ = make(failures=2, recoveries=2)
    assert feed(tracker, "xx..xx..") == ["opened", "resolved", "opened", "resolved"]


def test_second_incident_start_is_not_the_first() -> None:
    tracker, _ = make(failures=2, recoveries=1)
    feed(tracker, "xx.")
    tracker.record(False)
    transition = tracker.record(False)
    assert transition is not None
    assert transition.started_at == T0 + timedelta(seconds=90)


def test_restart_with_existing_down_state_keeps_the_incident() -> None:
    tracker, _ = make(failures=2, recoveries=2)
    feed(tracker, "xx")
    saved = tracker.state

    restarted = IncidentTracker(2, 2, FakeClock(), state=saved)
    assert restarted.record(False, T0 + timedelta(hours=1)) is None
    assert restarted.state.status is Status.DOWN


def test_restart_with_existing_down_state_still_needs_full_recovery() -> None:
    saved = CheckState(
        status=Status.DOWN,
        consecutive_failures=5,
        last_at=T0,
        incident_started_at=T0 - timedelta(minutes=5),
    )
    tracker = IncidentTracker(3, 2, FakeClock(), state=saved)
    assert tracker.record(True, T0 + timedelta(seconds=1)) is None
    transition = tracker.record(True, T0 + timedelta(seconds=2))
    assert transition is not None
    assert transition.started_at == T0 - timedelta(minutes=5)


def test_restart_with_partial_failure_streak_continues_counting() -> None:
    tracker, _ = make(failures=3)
    feed(tracker, "xx")
    restarted = IncidentTracker(3, 2, FakeClock(), state=tracker.state)
    transition = restarted.record(False, T0 + timedelta(minutes=10))
    assert transition is not None
    assert transition.kind is TransitionKind.OPENED
    assert transition.started_at == T0


def test_lowered_threshold_applies_to_restored_state() -> None:
    tracker, _ = make(failures=5)
    feed(tracker, "xxx")
    restarted = IncidentTracker(3, 2, FakeClock(), state=tracker.state)
    assert restarted.record(False, T0 + timedelta(minutes=1)) is not None


def test_out_of_order_result_is_ignored() -> None:
    tracker, _ = make(failures=2)
    tracker.record(False, T0 + timedelta(seconds=60))
    before = tracker.state
    assert tracker.record(False, T0) is None
    assert tracker.state == before


def test_late_stale_failure_cannot_open_an_incident() -> None:
    tracker, _ = make(failures=2)
    tracker.record(False, T0 + timedelta(seconds=60))
    tracker.record(True, T0 + timedelta(seconds=90))
    assert tracker.record(False, T0 + timedelta(seconds=70)) is None
    assert tracker.record(False, T0 + timedelta(seconds=80)) is None
    assert status(tracker) is Status.UP
    assert tracker.state.consecutive_failures == 0


def test_late_stale_success_cannot_resolve_an_incident() -> None:
    tracker, _ = make(failures=1, recoveries=1)
    tracker.record(False, T0 + timedelta(seconds=60))
    assert tracker.record(True, T0) is None
    assert status(tracker) is Status.DOWN


def test_same_timestamp_is_applied() -> None:
    tracker, _ = make(failures=2)
    tracker.record(False, T0)
    transition = tracker.record(False, T0)
    assert transition is not None


def test_timestamps_are_compared_across_timezones() -> None:
    later = datetime(2026, 1, 1, 14, 0, 30, tzinfo=timezone(timedelta(hours=2)))  # 12:00:30 UTC
    tracker, _ = make(failures=2)
    tracker.record(False, later)
    assert tracker.record(False, T0) is None  # 12:00:00 UTC is older
    assert tracker.state.consecutive_failures == 1


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate(CheckState(), True, datetime(2026, 1, 1), 3, 2)


@pytest.mark.parametrize(("failures", "recoveries"), [(0, 1), (1, 0), (-1, 2)])
def test_thresholds_must_be_positive(failures: int, recoveries: int) -> None:
    with pytest.raises(ValueError, match="thresholds"):
        IncidentTracker(failures, recoveries, FakeClock())
    with pytest.raises(ValueError, match="thresholds"):
        evaluate(CheckState(), True, T0, failures, recoveries)


def test_clock_is_used_when_no_timestamp_is_given() -> None:
    tracker, clock = make(failures=1)
    transition = tracker.record(False)
    assert transition is not None
    assert transition.at == T0
    assert clock.now == T0 + timedelta(seconds=30)


@pytest.mark.parametrize("pattern", ["x" * 10, ".x" * 20, "xx." * 10, "xxx..x.x" * 5])
def test_alert_count_never_exceeds_failure_streaks(pattern: str) -> None:
    tracker, _ = make(failures=3, recoveries=2)
    events = feed(tracker, pattern)
    assert events.count("opened") - events.count("resolved") in (0, 1)
    # alerts alternate: never two opens in a row
    for first, second in itertools.pairwise(events):
        assert first != second
