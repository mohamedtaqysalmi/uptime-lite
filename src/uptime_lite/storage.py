from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from uptime_lite.checks import CheckResult
from uptime_lite.incidents import CheckState, Status

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    check_name TEXT NOT NULL,
    at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    latency_ms REAL,
    status_code INTEGER,
    error TEXT
);
CREATE INDEX IF NOT EXISTS results_by_check ON results (check_name, at);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY,
    check_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    resolved_at TEXT,
    error TEXT
);
-- At most one open incident per check.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_incident
    ON incidents (check_name) WHERE resolved_at IS NULL;

CREATE TABLE IF NOT EXISTS check_state (
    check_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    consecutive_failures INTEGER NOT NULL,
    consecutive_successes INTEGER NOT NULL,
    last_at TEXT,
    streak_started_at TEXT,
    incident_started_at TEXT
);
"""


@dataclass(frozen=True)
class Incident:
    id: int
    check_name: str
    started_at: datetime
    resolved_at: datetime | None
    error: str | None


def _dump(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _load(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class Storage:
    """SQLite history. Writes only commit at the end of `transaction()`."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self._conn.close()
            raise RuntimeError(
                f"database schema version {version} is newer than this build ({SCHEMA_VERSION})"
            )
        self._conn.executescript(_SCHEMA)
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            yield
        except BaseException:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    def add_result(self, result: CheckResult) -> None:
        self._conn.execute(
            "INSERT INTO results (check_name, at, ok, latency_ms, status_code, error)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                result.check_name,
                _dump(result.at),
                int(result.ok),
                result.latency_ms,
                result.status_code,
                result.error,
            ),
        )

    def recent_results(self, check_name: str, limit: int = 100) -> list[CheckResult]:
        rows = self._conn.execute(
            "SELECT * FROM results WHERE check_name = ? ORDER BY at DESC, id DESC LIMIT ?",
            (check_name, limit),
        ).fetchall()
        return [
            CheckResult(
                check_name=r["check_name"],
                ok=bool(r["ok"]),
                at=_require(_load(r["at"])),
                latency_ms=r["latency_ms"],
                status_code=r["status_code"],
                error=r["error"],
            )
            for r in rows
        ]

    def load_state(self, check_name: str) -> CheckState:
        row = self._conn.execute(
            "SELECT * FROM check_state WHERE check_name = ?", (check_name,)
        ).fetchone()
        if row is None:
            return CheckState()
        return CheckState(
            status=Status(row["status"]),
            consecutive_failures=row["consecutive_failures"],
            consecutive_successes=row["consecutive_successes"],
            last_at=_load(row["last_at"]),
            streak_started_at=_load(row["streak_started_at"]),
            incident_started_at=_load(row["incident_started_at"]),
        )

    def save_state(self, check_name: str, state: CheckState) -> None:
        self._conn.execute(
            "INSERT INTO check_state (check_name, status, consecutive_failures,"
            " consecutive_successes, last_at, streak_started_at, incident_started_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (check_name) DO UPDATE SET status = excluded.status,"
            " consecutive_failures = excluded.consecutive_failures,"
            " consecutive_successes = excluded.consecutive_successes,"
            " last_at = excluded.last_at, streak_started_at = excluded.streak_started_at,"
            " incident_started_at = excluded.incident_started_at",
            (
                check_name,
                state.status.value,
                state.consecutive_failures,
                state.consecutive_successes,
                _dump(state.last_at),
                _dump(state.streak_started_at),
                _dump(state.incident_started_at),
            ),
        )

    def open_incident(self, check_name: str, started_at: datetime, error: str | None) -> None:
        self._conn.execute(
            "INSERT INTO incidents (check_name, started_at, error) VALUES (?, ?, ?)",
            (check_name, _dump(started_at), error),
        )

    def resolve_incident(self, check_name: str, resolved_at: datetime) -> None:
        self._conn.execute(
            "UPDATE incidents SET resolved_at = ? WHERE check_name = ? AND resolved_at IS NULL",
            (_dump(resolved_at), check_name),
        )

    def incidents(self, check_name: str | None = None) -> list[Incident]:
        query = "SELECT * FROM incidents"
        params: tuple[str, ...] = ()
        if check_name is not None:
            query += " WHERE check_name = ?"
            params = (check_name,)
        rows = self._conn.execute(query + " ORDER BY started_at, id", params).fetchall()
        return [_incident_from_row(r) for r in rows]

    def open_incidents(self) -> list[Incident]:
        rows = self._conn.execute(
            "SELECT * FROM incidents WHERE resolved_at IS NULL ORDER BY started_at, id"
        ).fetchall()
        return [_incident_from_row(r) for r in rows]


def _incident_from_row(row: sqlite3.Row) -> Incident:
    return Incident(
        id=row["id"],
        check_name=row["check_name"],
        started_at=_require(_load(row["started_at"])),
        resolved_at=_load(row["resolved_at"]),
        error=row["error"],
    )


def _require(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("unexpected NULL timestamp in database")
    return value
