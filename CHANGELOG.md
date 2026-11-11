# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffold: packaging, lint, type-check and test configuration.
- YAML config loader that validates every check and reports errors naming the check and field.
- HTTP and TCP check functions with injectable transports, timeouts and expected-status handling.
- Incident state machine with failure and recovery thresholds, an injected clock, and handling of out-of-order results.
- SQLite storage for check results, incidents and per-check state, so streaks survive a restart.
- Example config in `examples/config.example.yaml`.
