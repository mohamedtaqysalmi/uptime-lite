from __future__ import annotations

import logging

from uptime_lite.alerts import Alerter
from uptime_lite.checks import CheckResult, run_check, utc_now
from uptime_lite.config import CheckConfig, Config
from uptime_lite.incidents import Transition, TransitionKind, evaluate
from uptime_lite.storage import Storage

logger = logging.getLogger(__name__)


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


def handle_result(
    storage: Storage,
    check: CheckConfig,
    result: CheckResult,
    alerter: Alerter | None = None,
) -> Transition | None:
    """Process a result and notify alert channels when an incident opens or resolves."""
    transition = process_result(storage, check, result)
    if transition is not None and alerter is not None:
        alerter.notify(check.name, transition, result.error)
    return transition


def run_once(
    config: Config,
    storage: Storage,
    alerter: Alerter | None = None,
) -> list[tuple[CheckConfig, CheckResult, Transition | None]]:
    """Run every check once, persist results, and fire alerts on transitions."""
    outcomes: list[tuple[CheckConfig, CheckResult, Transition | None]] = []
    for check in config.checks:
        try:
            result = run_check(check)
        except Exception as exc:
            # One check hitting an unexpected error must not stop the others from running.
            logger.exception("check %r raised an unexpected error", check.name)
            error = f"internal error: {type(exc).__name__}"
            result = CheckResult(check.name, False, utc_now(), error=error)
        transition = handle_result(storage, check, result, alerter)
        outcomes.append((check, result, transition))
    return outcomes
