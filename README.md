# uptime-lite

Self-hosted uptime monitor with debounced incident detection and a static public status page.

Status: early scaffold, nothing usable yet.

The plan is HTTP and TCP checks on intervals, history in SQLite, incident detection with debounce, Telegram and webhook alerts, and a generated static status page, all driven by a YAML config that is validated at startup. None of that is built yet.

## Development

Requires Python 3.11 or newer.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; on Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Run the tests (coverage must stay at or above 85%):

```bash
pytest
```

Lint and type checks:

```bash
ruff check .
ruff format --check .
mypy
```

## License

MIT, see [LICENSE](LICENSE).
