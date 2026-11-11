# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
