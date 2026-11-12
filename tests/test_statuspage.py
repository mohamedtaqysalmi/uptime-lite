from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from uptime_lite.checks import CheckResult
from uptime_lite.config import CheckConfig, Config, StatusPageConfig
from uptime_lite.incidents import CheckState, Status
from uptime_lite.statuspage import collect_snapshots, render_html, write_status_page
from uptime_lite.storage import Storage

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _config(*names: str) -> Config:
    checks = tuple(CheckConfig(n, "http", f"https://example.com/{n}", 60, 5.0, 3, 2) for n in names)
    return Config(checks=checks, status_page=StatusPageConfig(title="Lab Status"))


def test_render_all_up(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "t.db")
    config = _config("web", "api")
    with storage.transaction():
        for name in ("web", "api"):
            storage.save_state(name, CheckState(status=Status.UP, last_at=T0))
            storage.add_result(CheckResult(name, True, T0, latency_ms=12.0, status_code=200))
    snapshots = collect_snapshots(config, storage)
    html = render_html(snapshots, StatusPageConfig(title="Lab Status"), generated_at=T0)
    assert "Lab Status" in html
    assert "All systems operational" in html
    assert "web" in html
    assert "api" in html
    assert 'class="pill up"' in html
    assert "2 of 2 services reporting" in html
    storage.close()


def test_render_down_and_incidents(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "t.db")
    config = _config("web")
    with storage.transaction():
        storage.save_state(
            "web",
            CheckState(
                status=Status.DOWN,
                consecutive_failures=3,
                last_at=T0,
                incident_started_at=T0 - timedelta(minutes=3),
            ),
        )
        storage.open_incident("web", T0 - timedelta(minutes=3), "timeout")
    html = render_html(
        collect_snapshots(config, storage),
        StatusPageConfig(title="Ops"),
        generated_at=T0,
    )
    assert "Service disruption" in html
    assert 'class="pill down"' in html
    assert "1 of 1 services down" in html
    assert "timeout" in html
    assert "Ongoing" in html
    storage.close()


def test_write_status_page_creates_index(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "t.db")
    config = _config("web")
    out = tmp_path / "public"
    path = write_status_page(config, storage, out, generated_at=T0)
    assert path == out / "index.html"
    assert path.is_file()
    assert "<title>Lab Status</title>" in path.read_text(encoding="utf-8")
    storage.close()


def test_check_that_never_ran_is_not_reported_as_operational(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "t.db")
    html = render_html(
        collect_snapshots(_config("web"), storage), StatusPageConfig(), generated_at=T0
    )
    assert "Waiting for the first check" in html
    assert 'class="pill unknown"' in html
    assert "All systems operational" not in html
    storage.close()


def test_names_and_errors_are_escaped(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "t.db")
    name = "<img src=x onerror=alert(1)>"
    config = _config(name)
    with storage.transaction():
        storage.save_state(name, CheckState(status=Status.DOWN, last_at=T0, incident_started_at=T0))
        storage.open_incident(name, T0, "</code><script>alert(2)</script>")
    html = render_html(
        collect_snapshots(config, storage), StatusPageConfig(title="<b>x</b>"), generated_at=T0
    )
    assert "<script>" not in html
    assert "<img" not in html
    assert "<b>" not in html
    assert "&lt;script&gt;" in html
    storage.close()


def test_resolved_incident_shows_duration_and_utc_times(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "t.db")
    config = _config("web")
    with storage.transaction():
        storage.save_state("web", CheckState(status=Status.UP, last_at=T0))
        storage.open_incident("web", T0 - timedelta(hours=2, minutes=5), "HTTP 503")
        storage.resolve_incident("web", T0 - timedelta(hours=1))
    html = render_html(collect_snapshots(config, storage), StatusPageConfig(), generated_at=T0)
    assert "Resolved" in html
    assert "(1 h 5 min)" in html
    assert "2026-01-01 09:55 UTC" in html
    storage.close()
