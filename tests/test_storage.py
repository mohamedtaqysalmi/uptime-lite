from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from uptime_lite.checks import CheckResult
from uptime_lite.config import CheckConfig
from uptime_lite.incidents import CheckState, Status, TransitionKind
from uptime_lite.monitor import process_result
from uptime_lite.storage import SCHEMA_VERSION, Storage

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
CHECK = CheckConfig("web", "http", "https://example.com", 60, 5.0, 2, 2)


def result(offset: int, ok: bool, name: str = "web") -> CheckResult:
    return CheckResult(
        name,
        ok,
        T0 + timedelta(seconds=offset),
        latency_ms=12.5 if ok else None,
        status_code=200 if ok else None,
        error=None if ok else "timeout",
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "uptime.db"


@pytest.fixture
def storage(db_path: Path) -> Iterator[Storage]:
    s = Storage(db_path)
    yield s
    s.close()


def test_results_round_trip_newest_first(storage: Storage) -> None:
    with storage.transaction():
        storage.add_result(result(0, True))
        storage.add_result(result(60, False))
        storage.add_result(result(30, True, name="other"))
    rows = storage.recent_results("web")
    assert [r.at for r in rows] == [T0 + timedelta(seconds=60), T0]
    assert rows[0] == result(60, False)
    assert rows[1] == result(0, True)


def test_recent_results_respects_limit(storage: Storage) -> None:
    with storage.transaction():
        for i in range(5):
            storage.add_result(result(i, True))
    assert len(storage.recent_results("web", limit=2)) == 2


def test_timestamps_are_normalised_to_utc(storage: Storage) -> None:
    local = T0.astimezone(timezone(timedelta(hours=5)))
    with storage.transaction():
        storage.add_result(CheckResult("web", True, local))
    assert storage.recent_results("web")[0].at == T0


def test_naive_timestamps_are_rejected(storage: Storage) -> None:
    with pytest.raises(ValueError, match="timezone-aware"), storage.transaction():
        storage.add_result(CheckResult("web", True, datetime(2026, 1, 1)))


def test_state_defaults_and_round_trip(storage: Storage) -> None:
    assert storage.load_state("web") == CheckState()
    state = CheckState(
        status=Status.DOWN,
        consecutive_failures=4,
        consecutive_successes=1,
        last_at=T0,
        streak_started_at=None,
        incident_started_at=T0 - timedelta(minutes=3),
    )
    with storage.transaction():
        storage.save_state("web", state)
        storage.save_state("web", state)  # upsert
    assert storage.load_state("web") == state


def test_transaction_rolls_back_on_error(storage: Storage) -> None:
    def failing_write() -> None:
        with storage.transaction():
            storage.add_result(result(0, True))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        failing_write()
    assert storage.recent_results("web") == []


def test_only_one_open_incident_per_check(storage: Storage) -> None:
    with storage.transaction():
        storage.open_incident("web", T0, "timeout")
    with pytest.raises(sqlite3.IntegrityError), storage.transaction():
        storage.open_incident("web", T0, "timeout")


def test_resolve_without_open_incident_is_a_no_op(storage: Storage) -> None:
    with storage.transaction():
        storage.resolve_incident("web", T0)
    assert storage.incidents() == []


def test_incidents_can_be_filtered_by_check(storage: Storage) -> None:
    with storage.transaction():
        storage.open_incident("web", T0, None)
        storage.open_incident("db", T0 + timedelta(seconds=1), "refused")
    assert [i.check_name for i in storage.incidents()] == ["web", "db"]
    assert [i.check_name for i in storage.incidents("db")] == ["db"]


def test_schema_version_is_recorded_and_newer_databases_are_refused(db_path: Path) -> None:
    Storage(db_path).close()
    conn = sqlite3.connect(db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="newer than this build"):
        Storage(db_path)


def test_in_memory_database_works() -> None:
    s = Storage(":memory:")
    with s.transaction():
        s.add_result(result(0, True))
    assert len(s.recent_results("web")) == 1
    s.close()


# process_result ties the state machine to the database.


def test_full_incident_lifecycle(storage: Storage) -> None:
    transitions = [
        process_result(storage, CHECK, result(i * 30, ok))
        for i, ok in enumerate([True, False, False, False, True, True])
    ]
    kinds = [t.kind if t else None for t in transitions]
    assert kinds == [None, None, TransitionKind.OPENED, None, None, TransitionKind.RESOLVED]
    (incident,) = storage.incidents("web")
    assert incident.started_at == T0 + timedelta(seconds=30)
    assert incident.resolved_at == T0 + timedelta(seconds=150)
    assert incident.error == "timeout"
    assert len(storage.recent_results("web")) == 6


def test_state_survives_a_restart(db_path: Path) -> None:
    first = Storage(db_path)
    assert process_result(first, CHECK, result(0, False)) is None
    first.close()

    second = Storage(db_path)
    transition = process_result(second, CHECK, result(30, False))
    assert transition is not None
    assert transition.kind is TransitionKind.OPENED
    assert transition.started_at == T0
    second.close()

    third = Storage(db_path)
    assert process_result(third, CHECK, result(60, False)) is None  # still one incident
    assert process_result(third, CHECK, result(90, True)) is None
    resolved = process_result(third, CHECK, result(120, True))
    assert resolved is not None
    assert resolved.kind is TransitionKind.RESOLVED
    assert len(third.incidents()) == 1
    third.close()


def test_stale_result_is_stored_but_does_not_change_state(storage: Storage) -> None:
    process_result(storage, CHECK, result(60, False))
    before = storage.load_state("web")
    assert process_result(storage, CHECK, result(0, False)) is None
    assert storage.load_state("web") == before
    assert len(storage.recent_results("web")) == 2


def test_checks_are_tracked_independently(storage: Storage) -> None:
    other = CheckConfig("db", "tcp", "192.0.2.10:5432", 60, 3.0, 1, 1)
    process_result(storage, CHECK, result(0, False))
    assert process_result(storage, other, result(0, False, name="db")) is not None
    assert [i.check_name for i in storage.incidents()] == ["db"]
