"""Debounced incident detection. Pure logic: no I/O, time comes from the caller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum


class Status(StrEnum):
    UP = "up"
    DOWN = "down"


class TransitionKind(StrEnum):
    OPENED = "opened"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class CheckState:
    status: Status = Status.UP
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    # Time of the last result that was applied; older results are dropped.
    last_at: datetime | None = None
    # First result of the current failing streak while still UP.
    streak_started_at: datetime | None = None
    # Set while status is DOWN: when the first failure of the incident happened.
    incident_started_at: datetime | None = None


@dataclass(frozen=True)
class Transition:
    kind: TransitionKind
    # When the threshold was crossed, i.e. the timestamp of the deciding result.
    at: datetime
    # When the incident's first failure happened.
    started_at: datetime


def evaluate(
    state: CheckState,
    ok: bool,
    at: datetime,
    failure_threshold: int,
    recovery_threshold: int,
) -> tuple[CheckState, Transition | None]:
    """Apply one check result and return the new state and a transition, if any.

    A check goes DOWN after `failure_threshold` consecutive failures and back UP
    after `recovery_threshold` consecutive successes. Any result of the opposite
    kind resets the streak, which is what keeps a flapping check quiet.

    A result timestamped before `last_at` is stale (for example a slow check that
    finished after a newer one) and is ignored. A result with the same timestamp is
    applied.
    """
    if failure_threshold < 1 or recovery_threshold < 1:
        raise ValueError("thresholds must be >= 1")
    if at.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    if state.last_at is not None and at < state.last_at:
        return state, None

    if state.status is Status.UP:
        return _when_up(state, ok, at, failure_threshold)
    return _when_down(state, ok, at, recovery_threshold)


def _when_up(
    state: CheckState, ok: bool, at: datetime, failure_threshold: int
) -> tuple[CheckState, Transition | None]:
    if ok:
        return CheckState(status=Status.UP, last_at=at), None

    failures = state.consecutive_failures + 1
    started = state.streak_started_at if state.consecutive_failures else at
    assert started is not None
    if failures < failure_threshold:
        new = CheckState(
            status=Status.UP,
            consecutive_failures=failures,
            last_at=at,
            streak_started_at=started,
        )
        return new, None
    new = CheckState(
        status=Status.DOWN,
        consecutive_failures=failures,
        last_at=at,
        incident_started_at=started,
    )
    return new, Transition(TransitionKind.OPENED, at=at, started_at=started)


def _when_down(
    state: CheckState, ok: bool, at: datetime, recovery_threshold: int
) -> tuple[CheckState, Transition | None]:
    if not ok:
        return replace(
            state,
            consecutive_failures=state.consecutive_failures + 1,
            consecutive_successes=0,
            last_at=at,
        ), None

    successes = state.consecutive_successes + 1
    if successes < recovery_threshold:
        return replace(
            state,
            consecutive_failures=0,
            consecutive_successes=successes,
            last_at=at,
        ), None
    started = state.incident_started_at
    assert started is not None
    return CheckState(status=Status.UP, last_at=at), Transition(
        TransitionKind.RESOLVED, at=at, started_at=started
    )


class IncidentTracker:
    """Holds the state of one check. `clock` supplies the time when none is given."""

    def __init__(
        self,
        failure_threshold: int,
        recovery_threshold: int,
        clock: Callable[[], datetime],
        state: CheckState | None = None,
    ) -> None:
        if failure_threshold < 1 or recovery_threshold < 1:
            raise ValueError("thresholds must be >= 1")
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.state = state or CheckState()
        self._clock = clock

    def record(self, ok: bool, at: datetime | None = None) -> Transition | None:
        self.state, transition = evaluate(
            self.state,
            ok,
            at if at is not None else self._clock(),
            self.failure_threshold,
            self.recovery_threshold,
        )
        return transition
