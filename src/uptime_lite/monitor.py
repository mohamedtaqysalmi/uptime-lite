from __future__ import annotations

from uptime_lite.checks import CheckResult
from uptime_lite.config import CheckConfig
from uptime_lite.incidents import Transition, TransitionKind, evaluate
from uptime_lite.storage import Storage


def process_result(storage: Storage, check: CheckConfig, result: CheckResult) -> Transition | None:
    """Store a result, advance the check's persisted state and open or resolve incidents.

    Everything happens in one transaction, so after a crash the stored state and the
    incidents table always agree. A stale result (older than the last applied one) is
    still kept in the history but does not change the state.
    """
    with storage.transaction():
        storage.add_result(result)
        state = storage.load_state(check.name)
        new_state, transition = evaluate(
            state, result.ok, result.at, check.failure_threshold, check.recovery_threshold
        )
        if new_state != state:
            storage.save_state(check.name, new_state)
        if transition is None:
            return None
        if transition.kind is TransitionKind.OPENED:
            storage.open_incident(check.name, transition.started_at, result.error)
        else:
            storage.resolve_incident(check.name, transition.at)
        return transition
