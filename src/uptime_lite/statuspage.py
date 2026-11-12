"""Generate a static HTML status page from stored check state and incidents."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from uptime_lite.config import CheckConfig, Config, StatusPageConfig
from uptime_lite.incidents import Status
from uptime_lite.storage import Incident, Storage


@dataclass(frozen=True)
class CheckSnapshot:
    check: CheckConfig
    status: Status
    last_at: datetime | None
    open_incident: Incident | None
    recent_incidents: tuple[Incident, ...]


def collect_snapshots(config: Config, storage: Storage, history: int = 5) -> list[CheckSnapshot]:
    open_by_check = {i.check_name: i for i in storage.open_incidents()}
    snapshots: list[CheckSnapshot] = []
    for check in config.checks:
        state = storage.load_state(check.name)
        incidents = storage.incidents(check.name)
        recent = tuple(reversed(incidents[-history:])) if incidents else ()
        snapshots.append(
            CheckSnapshot(
                check=check,
                status=state.status,
                last_at=state.last_at,
                open_incident=open_by_check.get(check.name),
                recent_incidents=recent,
            )
        )
    return snapshots


_CSS = """
:root {
  --bg: #ffffff; --surface: #f8f9fa; --ink: #202122; --muted: #54595d;
  --line: #a2a9b1; --line-soft: #c8ccd1; --ok: #14633a; --bad: #b32424;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --serif: Georgia, "Times New Roman", Times, serif;
  --mono: ui-monospace, Menlo, Consolas, "Liberation Mono", "Courier New", monospace;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #101418; --surface: #1b2026; --ink: #eaecf0; --muted: #a2a9b1;
    --line: #54595d; --line-soft: #3a4046; --ok: #7fd1a0; --bad: #ff9a8f;
  }
}
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 1rem/1.6 var(--sans); overflow-wrap: break-word; }
main { max-width: 52rem; margin: 0 auto; padding: 1.25rem 1rem 2.5rem; }
h1, h2 { margin: 0; font-family: var(--serif); font-weight: 400; line-height: 1.3; border-bottom: 1px solid var(--line); }
h1 { font-size: 2rem; padding-bottom: 0.2rem; }
h2 { margin-top: 1.75rem; font-size: 1.5rem; padding-bottom: 0.15rem; }
.meta { margin: 0.5rem 0 0; color: var(--muted); font-size: 0.875rem; }
.banner { margin-top: 1rem; padding: 0.6rem 0.75rem; border: 1px solid var(--line-soft); border-left: 4px solid var(--muted); background: var(--surface); }
.banner.up { border-left-color: var(--ok); }
.banner.down { border-left-color: var(--bad); }
.banner strong { display: block; }
.banner span { color: var(--muted); font-size: 0.875rem; }
.table-wrap { margin-top: 0.75rem; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
th, td { padding: 0.35rem 0.6rem; text-align: left; vertical-align: top; border: 1px solid var(--line); }
th { background: var(--surface); white-space: nowrap; }
.type { display: block; color: var(--muted); font: 0.8rem var(--mono); }
.pill { font-weight: 700; white-space: nowrap; }
.pill.up { color: var(--ok); }
.pill.down { color: var(--bad); }
.pill.unknown { color: var(--muted); }
ul { margin: 0.75rem 0 0; padding-left: 1.4rem; }
li + li { margin-top: 0.5rem; }
li .detail { display: block; color: var(--muted); font-size: 0.875rem; }
code { font: 0.875em var(--mono); background: var(--surface); border: 1px solid var(--line-soft); border-radius: 2px; padding: 0 0.25em; }
.empty { margin: 0.75rem 0 0; color: var(--muted); }
footer { margin-top: 2rem; padding-top: 0.75rem; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.875rem; }
"""


def render_html(
    snapshots: list[CheckSnapshot],
    page: StatusPageConfig,
    *,
    generated_at: datetime,
) -> str:
    kinds = [_kind(s) for s in snapshots]
    down = kinds.count("down")
    up = kinds.count("up")
    if down:
        overall, headline = "down", "Service disruption"
        sub = f"{down} of {len(kinds)} services down"
    elif up:
        overall, headline = "up", "All systems operational"
        sub = f"{up} of {len(kinds)} services reporting"
    else:
        overall, headline = "unknown", "Waiting for the first check"
        sub = "No results recorded yet"
    services = "\n".join(_check_row(s) for s in snapshots)
    incidents = [inc for s in snapshots for inc in s.recent_incidents]
    incidents.sort(key=lambda i: i.started_at, reverse=True)
    if incidents:
        incident_block = "<ul>\n" + "\n".join(_incident_row(i) for i in incidents) + "\n</ul>"
    else:
        incident_block = '<p class="empty">No incidents recorded.</p>'
    title = html.escape(page.title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="Current status and recent incidents for {title}">
<style>{_CSS}</style>
</head>
<body>
<main>
<header>
<h1>{title}</h1>
<p class="meta">Generated {html.escape(_fmt(generated_at))}</p>
</header>
<div class="banner {overall}" role="status">
<div><strong>{headline}</strong><span>{html.escape(sub)}</span></div>
</div>
<section aria-labelledby="services-title">
<h2 id="services-title">Services</h2>
<div class="table-wrap">
<table>
<thead><tr><th scope="col">Service</th><th scope="col">Status</th><th scope="col">Last check</th></tr></thead>
<tbody>
{services}
</tbody>
</table>
</div>
</section>
<section aria-labelledby="incidents-title">
<h2 id="incidents-title">Recent incidents</h2>
{incident_block}
</section>
<footer>Generated by <code>uptime-lite</code>. Times are UTC.</footer>
</main>
</body>
</html>
"""


def write_status_page(
    config: Config,
    storage: Storage,
    output_dir: str | Path,
    *,
    generated_at: datetime,
    history: int = 5,
) -> Path:
    page = config.status_page or StatusPageConfig()
    snapshots = collect_snapshots(config, storage, history=history)
    html_text = render_html(snapshots, page, generated_at=generated_at)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(html_text, encoding="utf-8")
    return path


_LABELS = {"up": "Up", "down": "Down", "unknown": "No data yet"}


def _kind(snapshot: CheckSnapshot) -> str:
    if snapshot.last_at is None:
        return "unknown"
    return snapshot.status.value


def _check_row(snapshot: CheckSnapshot) -> str:
    kind = _kind(snapshot)
    last = _fmt(snapshot.last_at) if snapshot.last_at else "never"
    return (
        "<tr>"
        f"<td>{html.escape(snapshot.check.name)}"
        f'<span class="type">{html.escape(snapshot.check.type)}</span></td>'
        f'<td><span class="pill {kind}">{_LABELS[kind]}</span></td>'
        f"<td>{html.escape(last)}</td>"
        "</tr>"
    )


def _incident_row(incident: Incident) -> str:
    if incident.resolved_at is None:
        state, kind = "Ongoing", "down"
        timing = f"Started {_fmt(incident.started_at)}"
    else:
        state, kind = "Resolved", "up"
        length = _duration(incident.resolved_at - incident.started_at)
        timing = f"{_fmt(incident.started_at)} to {_fmt(incident.resolved_at)} ({length})"
    error = f"<code>{html.escape(incident.error)}</code>" if incident.error else ""
    return (
        "<li>"
        f"<strong>{html.escape(incident.check_name)}</strong> "
        f'<span class="pill {kind}">{state}</span>'
        f'<span class="detail">{html.escape(timing)} {error}</span>'
        "</li>"
    )


def _duration(delta: timedelta) -> str:
    minutes = max(int(delta.total_seconds() // 60), 0)
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    if hours == 0:
        return f"{minutes} min"
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
