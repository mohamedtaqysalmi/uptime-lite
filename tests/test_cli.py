from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from uptime_lite.checks import CheckResult
from uptime_lite.cli import main
from uptime_lite.config import CheckConfig
from uptime_lite.monitor import handle_result
from uptime_lite.storage import Storage

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

MINIMAL = """
checks:
  - name: web
    type: http
    target: https://example.com/
    failure_threshold: 1
    recovery_threshold: 1
status_page:
  title: Demo Status
"""


def test_status_page_command(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text(MINIMAL, encoding="utf-8")
    db = tmp_path / "u.db"
    storage = Storage(db)
    check = CheckConfig("web", "http", "https://example.com/", 60, 10.0, 1, 1)
    handle_result(storage, check, CheckResult("web", True, T0, latency_ms=5.0, status_code=200))
    storage.close()
    out = tmp_path / "status"
    assert main(["status-page", "-c", str(cfg), "-d", str(db), "-o", str(out)]) == 0
    assert (out / "index.html").is_file()
    text = (out / "index.html").read_text(encoding="utf-8")
    assert "Demo Status" in text


def test_check_command_with_injected_failure_via_bad_config_path(tmp_path: Path) -> None:
    assert main(["check", "-c", str(tmp_path / "missing.yaml")]) == 2
