#!/usr/bin/env python3
"""Regenerate site/status/index.html from made-up check results.

The results are synthetic: they are written to a throwaway database through the same
code path real results take, then the real `uptime-lite status-page` command renders
the page. Nothing here touches the network.

    python scripts/generate_example_status.py
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

from uptime_lite.checks import CheckResult, utc_now
from uptime_lite.cli import main
from uptime_lite.config import load_config
from uptime_lite.monitor import process_result
from uptime_lite.storage import Storage

ROOT = Path(__file__).resolve().parent.parent
STEPS = 36  # one result every 10 minutes for the last six hours
SPACING = timedelta(minutes=10)

# Which step numbers fail for each check in examples/config.example.yaml.
FAILURES: dict[str, dict[int, str]] = {
    "example-website": {},
    # Single blip: debounced, never becomes an incident.
    "example-ssh": {10: "timeout"},
    # Two failures in a row open an incident (threshold 2), two passes resolve it.
    "example-database": {
        20: "ConnectionRefusedError: connection refused",
        21: "ConnectionRefusedError: connection refused",
    },
    # Still failing at the end, so the page shows an open incident.
    "example-api-health": dict.fromkeys(range(32, STEPS), "unexpected status 503"),
}


def main_script() -> None:
    config = load_config(ROOT / "examples" / "config.example.yaml")
    now = utc_now()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "example.db"
        storage = Storage(db)
        for step in range(STEPS):
            at = now - SPACING * (STEPS - 1 - step)
            for check in config.checks:
                error = FAILURES[check.name].get(step)
                result = CheckResult(
                    check.name,
                    ok=error is None,
                    at=at,
                    latency_ms=None if error else 40.0 + step % 7,
                    status_code=None if error or check.type == "tcp" else 200,
                    error=error,
                )
                process_result(storage, check, result)
        storage.close()
        main(
            [
                "status-page",
                "-c",
                str(ROOT / "examples" / "config.example.yaml"),
                "-d",
                str(db),
                "-o",
                str(ROOT / "site" / "status"),
            ]
        )


if __name__ == "__main__":
    main_script()
