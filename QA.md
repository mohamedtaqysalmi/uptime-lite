# QA notes (v0.1.0)

Manual and automated checks before tagging. Automated results live in [TEST_REPORT.md](TEST_REPORT.md).

## Scope

In scope: YAML config validation, HTTP/TCP checks, incident debounce, SQLite history, Telegram/webhook alerts, static status page generation, CLI (`check`, `status-page`), Pages landing + example status, resource notes.

Out of scope for this tag: interval scheduler daemon, Docker image, PyPI publish, live Pages feed from a running monitor, Lighthouse CI automation.

## Test strategy

| Layer | What | Why |
| --- | --- | --- |
| Unit | `incidents.evaluate`, config validation, alert formatting | Flapping logic and bad configs are the costly bugs |
| Unit (injected I/O) | checks, alerts, storage, statuspage | No real network; fake clock and fake HTTP poster |
| CLI smoke | `status-page` and bad-config exit codes | Confirms entry points without a live probe target |
| Manual | Pages + one real check against a URL you own | Captures what unit tests cannot see |

## Automated gate (must be green)

| Check | Command / place |
| --- | --- |
| Lint | `ruff check .` |
| Format | `ruff format --check .` |
| Types | `mypy` |
| Tests + coverage ≥ 85% | `pytest` |
| Wheel build | `python -m build` (CI) |
| CI matrix | Python 3.11 and 3.14 on `ubuntu-latest` |

## Manual checklist (human)

| Step | Expected | Pass? |
| --- | --- | --- |
| Open https://mohamedtaqysalmi.github.io/uptime-lite/ after Pages deploy | Landing loads, brand visible, no horizontal scroll at ~360px | |
| Example status iframe / link | Shows mixed up/down demo with incident rows | |
| Copy-commands button | Copies quickstart block in Chromium | |
| Dark / light OS theme | Text readable on hero and panels | |
| Keyboard: Tab to skip link, CTAs, copy button | Focus visible | |
| `uptime-lite check -c examples/config.example.yaml --no-alerts` | Runs (targets may fail; process should not crash) | |
| Generate status page from a local DB | `status/index.html` lists configured checks | |
| Record demo GIF for README | Placeholder instructions followed | |

## Known gaps

- No interval scheduler; cron must call `check`.
- Alert channels not exercised against real Telegram/webhook in CI.
- Lighthouse scores not recorded (see below).

## Lighthouse

Not measured yet ([issue 11](https://github.com/mohamedtaqysalmi/uptime-lite/issues/11)).

## Sign-off

Automated gate: see TEST_REPORT.md for the local run used at tag time. CI on `main` after squash-merge is the public record.
