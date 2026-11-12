"""Command-line entry points for one-shot checks and status page generation."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from uptime_lite.alerts import Alerter
from uptime_lite.checks import utc_now
from uptime_lite.config import Config, ConfigError, load_config
from uptime_lite.monitor import run_once
from uptime_lite.statuspage import write_status_page
from uptime_lite.storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uptime-lite",
        description="Self-hosted uptime checks with debounced incidents and a static status page.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Run every configured check once and store results")
    check.add_argument("-c", "--config", required=True, type=Path, help="Path to YAML config")
    check.add_argument(
        "-d",
        "--db",
        type=Path,
        default=Path("uptime.db"),
        help="SQLite database path (default: uptime.db)",
    )
    check.add_argument(
        "--no-alerts",
        action="store_true",
        help="Skip Telegram/webhook notifications even if configured",
    )
    check.add_argument("-v", "--verbose", action="store_true")

    page = sub.add_parser("status-page", help="Write a static status page from the database")
    page.add_argument("-c", "--config", required=True, type=Path, help="Path to YAML config")
    page.add_argument(
        "-d",
        "--db",
        type=Path,
        default=Path("uptime.db"),
        help="SQLite database path (default: uptime.db)",
    )
    page.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("status"),
        help="Output directory for index.html (default: status)",
    )
    page.add_argument("-v", "--verbose", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "status-page" and not args.db.is_file():
        # Opening it would create an empty database and publish a page that says nothing ran.
        print(f"database not found: {args.db} (run `uptime-lite check` first)", file=sys.stderr)
        return 2

    storage = Storage(args.db)
    try:
        if args.command == "check":
            return _cmd_check(config, storage, args.no_alerts)
        if args.command == "status-page":
            path = write_status_page(config, storage, args.output, generated_at=utc_now())
            print(f"wrote {path}")
            return 0
    finally:
        storage.close()
    parser.error(f"unknown command {args.command!r}")
    return 2


def _cmd_check(config: Config, storage: Storage, no_alerts: bool) -> int:
    alerter = None
    if not no_alerts and config.alerts is not None:
        alerter = Alerter(config.alerts)
    outcomes = run_once(config, storage, alerter)
    failed = 0
    for check, result, transition in outcomes:
        mark = "ok" if result.ok else "FAIL"
        extra = ""
        if transition is not None:
            extra = f" [{transition.kind.value}]"
        latency = f" {result.latency_ms:.0f}ms" if result.latency_ms is not None else ""
        detail = f" {result.error}" if result.error else ""
        print(f"{mark:4} {check.name}{latency}{detail}{extra}")
        if not result.ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
