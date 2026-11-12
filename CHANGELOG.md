# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- A hostname the standard library cannot encode (for example a label over 63 characters) crashed `uptime-lite check`; it now fails that check.
- An unexpected error in one check no longer stops the remaining checks in the run.
- Alert delivery caught only `OSError`. Other errors from the HTTP client escaped, skipped the second channel, and could print the Telegram bot token in a traceback.
- Alert times are UTC instead of the machine's local timezone.
- `expected_status` with a 3xx code could never match because redirects are followed; the config now rejects it.
- `status-page` created an empty database when `-d` pointed at a missing file; it now exits with an error.
- The status page is written atomically, and only the newest incidents are read from the database.
- Resource usage is now measured on a real `check` run (memory, CPU, method and machine documented), replacing numbers taken with stub transports.

### Removed

- `IncidentTracker` moved into the tests; nothing in the package used it.

## [0.1.0] - 2026-11-11

### Added

- YAML config loader with named field errors for checks, alerts and status page settings.
- HTTP and TCP check functions with injectable transports.
- Incident state machine with failure/recovery thresholds and out-of-order handling.
- SQLite storage for results, incidents and per-check state.
- Telegram and webhook alerts on incident open/resolve (tokens from the environment).
- Static status page generator and CLI (`uptime-lite check`, `uptime-lite status-page`).
- Resource usage notes for 20 fake checks.
- GitHub Pages landing with an example status snapshot.
- QA notes, architecture ADRs and community/CI scaffolding.

## [0.0.1] - 2026-11-11

### Added

- Project scaffold: packaging, lint, type-check and test configuration.
