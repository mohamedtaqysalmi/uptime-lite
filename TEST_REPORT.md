# Test report: v0.1.0 plus review fixes

Date: 2026-11-12  
Environment: Windows 11, Python 3.15.2 (local `.venv`), package installed editable with `[dev]`.  
CI also runs the same gate on Ubuntu with Python 3.11 and 3.14.

## Commands

```bash
ruff check .
ruff format --check .
mypy
pytest
```

## Results (local)

| Check | Result |
| --- | --- |
| ruff check | pass |
| ruff format --check | pass |
| mypy (strict) | pass |
| pytest | **161 passed** |
| Coverage (branch) | **90.31%** (fail_under 85) |

## What is covered

- Config validation for checks, alerts and status_page (including token-in-YAML rejection).
- HTTP/TCP checks with injected transports and expected-status handling.
- Incident state machine with exact thresholds, flap patterns, restored state and stale timestamps.
- SQLite results, state, open/resolve incidents, rollback.
- Telegram/webhook alerter with injectable poster (missing token, HTTP errors, bearer).
- Status page render/write and CLI `status-page` / bad-config paths.
- `handle_result` notifying on open transitions, and one crashing check not stopping the rest of a run.
- The default HTTP poster and check transports against a throwaway loopback server.

## What is not covered

- Real Telegram Bot API or a live webhook receiver.
- Real network probes in CI (example.com targets may fail; `--no-alerts` local smoke is manual).
- Interval scheduler (not shipped).
- Browser/Playwright smoke of the Pages site (manual checklist in QA.md).
- A long-running process: memory and CPU were measured only for single `check` runs (see docs/resource-usage.md).
- The CLI `check` command end to end (tracked in issue 8).

Public CI on `main` after merge is the lasting record for the matrix.
