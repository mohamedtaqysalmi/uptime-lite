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
    assert 'class="status up"' in html
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
    assert 'class="status down"' in html
    assert "timeout" in html
    assert "open" in html
    storage.close()


def test_write_status_page_creates_index(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "t.db")
    config = _config("web")
    out = tmp_path / "public"
    path = write_status_page(config, storage, out, generated_at=T0)
    assert path == out / "index.html"
    assert path.is_file()
    assert "Status" in path.read_text(encoding="utf-8") or "Lab Status" in path.read_text(
        encoding="utf-8"
    )
    storage.close()
