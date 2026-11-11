# Test report — v0.1.0

Date: 2026-11-11  
Environment: Windows 10, Python 3.15.2 (local `.venv`), package installed editable with `[dev]`.  
CI also runs the same gate on Ubuntu with Python 3.11 and 3.14.

## Commands

```bash
ruff check .
ruff format --check .
mypy
pytest
```

## Results (local, pre-tag)

| Check | Result |
| --- | --- |
| ruff check | pass |
| ruff format --check | pass |
| mypy (strict) | pass |
| pytest | **147 passed** |
| Coverage (branch) | **88.12%** (fail_under 85) |

## What is covered

- Config validation for checks, alerts and status_page (including token-in-YAML rejection).
- HTTP/TCP checks with injected transports and expected-status handling.
- Incident state machine with fake clock, flap patterns and stale timestamps.
- SQLite results, state, open/resolve incidents, rollback.
- Telegram/webhook alerter with injectable poster (missing token, HTTP errors, bearer).
- Status page render/write and CLI `status-page` / bad-config paths.
- `handle_result` notifying on open transitions.

## What is not covered

- Real Telegram Bot API or a live webhook receiver.
- Real network probes in CI (example.com targets may fail; `--no-alerts` local smoke is manual).
- Interval scheduler (not shipped).
- Browser/Playwright smoke of the Pages site (manual checklist in QA.md).
- Process RSS under load (only tracemalloc + CPU/wall for 20 fake checks).

Public CI on `main` after merge is the lasting record for the matrix.
