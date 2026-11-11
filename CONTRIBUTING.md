# Contributing

This project is maintained by one person. Replies to issues and pull requests may take a few days. Small, focused changes get reviewed faster than large ones.

The project is at an early stage, so please open an issue before starting anything bigger than a bug fix or a typo.

## Setup

You need Python 3.11 or newer.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; on Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Tests and checks

CI runs all of these on Python 3.11 and 3.14. Run them locally before opening a PR:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

`pytest` reports coverage and fails below 85%. New code should come with tests.

## Branches and commits

- Branch from `main`. Name branches `type/short-description`, for example `feat/tcp-check` or `fix/debounce-reset`.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`).
- `main` only changes through pull requests, which are squash-merged. The PR title becomes the commit message, so write it as a Conventional Commit.

## Pull requests

- Fill in the template: what changed, why, and how you tested it.
- Keep one concern per PR.
- CI must be green. If a check fails, fix the cause rather than loosening the check.
- Update `CHANGELOG.md` under Unreleased for anything a user would notice.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).
