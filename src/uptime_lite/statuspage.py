"""Generate a static HTML status page from stored check state and incidents."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
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


def render_html(
    snapshots: list[CheckSnapshot],
    page: StatusPageConfig,
    *,
    generated_at: datetime,
) -> str:
    overall = (
        Status.UP
        if all(s.status is Status.UP for s in snapshots)
        else Status.DOWN
        if any(s.status is Status.DOWN for s in snapshots)
        else Status.UP
    )
    rows = "\n".join(_check_row(s) for s in snapshots)
    incident_rows = "\n".join(_incident_row(inc) for s in snapshots for inc in s.recent_incidents)
    if not incident_rows:
        incident_rows = '<tr><td colspan="4">No incidents recorded yet.</td></tr>'
    title = html.escape(page.title)
    overall_label = "All systems operational" if overall is Status.UP else "Service disruption"
    overall_class = "up" if overall is Status.UP else "down"
    generated = html.escape(_fmt(generated_at))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <meta name="description" content="Public status for {title}" />
  <style>
    :root {{
      --bg: #0f1419;
      --panel: #171e26;
      --text: #e7eef5;
      --muted: #8b9aab;
      --up: #2fbf71;
      --down: #e35d6a;
      --line: #2a3542;
      --accent: #3db8a8;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f4f7fa;
        --panel: #ffffff;
        --text: #14202b;
        --muted: #5c6b7a;
        --line: #d5dee7;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    main {{ max-width: 52rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
    h1 {{ font-size: 1.75rem; margin: 0 0 0.5rem; letter-spacing: -0.02em; }}
    .banner {{
      display: flex; align-items: center; gap: 0.75rem;
      padding: 1rem 1.1rem; border-radius: 0.5rem;
      background: var(--panel); border: 1px solid var(--line); margin: 1.25rem 0 2rem;
    }}
    .dot {{ width: 0.7rem; height: 0.7rem; border-radius: 50%; background: var(--muted); }}
    .dot.up {{ background: var(--up); }}
    .dot.down {{ background: var(--down); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel);
      border: 1px solid var(--line); border-radius: 0.5rem; overflow: hidden; }}
    th, td {{ text-align: left; padding: 0.75rem 0.9rem; border-bottom: 1px solid var(--line);
      vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 500; font-size: 0.85rem; }}
    tr:last-child td {{ border-bottom: none; }}
    .status {{
      font-weight: 600; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.04em;
    }}
    .status.up {{ color: var(--up); }}
    .status.down {{ color: var(--down); }}
    .muted {{ color: var(--muted); font-size: 0.9rem; }}
    h2 {{ font-size: 1.1rem; margin: 2.25rem 0 0.75rem; }}
    footer {{ margin-top: 2rem; color: var(--muted); font-size: 0.85rem; }}
    code {{ font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.85em; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p class="muted">Generated {generated}</p>
    <div class="banner" role="status">
      <span class="dot {overall_class}" aria-hidden="true"></span>
      <strong>{overall_label}</strong>
    </div>
    <h2>Services</h2>
    <table>
      <thead>
        <tr><th>Name</th><th>Type</th><th>Status</th><th>Last check</th></tr>
      </thead>
      <tbody>
{rows}
      </tbody>
    </table>
    <h2>Recent incidents</h2>
    <table>
      <thead>
        <tr><th>Service</th><th>Started</th><th>Resolved</th><th>Detail</th></tr>
      </thead>
      <tbody>
{incident_rows}
      </tbody>
    </table>
    <footer>
      Static page from <code>uptime-lite</code>.
      Refresh by regenerating after checks run.
    </footer>
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


def _check_row(snapshot: CheckSnapshot) -> str:
    status_class = snapshot.status.value
    last = _fmt(snapshot.last_at) if snapshot.last_at else "—"
    return (
        "<tr>"
        f"<td>{html.escape(snapshot.check.name)}</td>"
        f"<td><code>{html.escape(snapshot.check.type)}</code></td>"
        f'<td class="status {status_class}">{html.escape(snapshot.status.value)}</td>'
        f'<td class="muted">{html.escape(last)}</td>'
        "</tr>"
    )


def _incident_row(incident: Incident) -> str:
    resolved = _fmt(incident.resolved_at) if incident.resolved_at else "open"
    detail = html.escape(incident.error or "—")
    return (
        "<tr>"
        f"<td>{html.escape(incident.check_name)}</td>"
        f'<td class="muted">{html.escape(_fmt(incident.started_at))}</td>'
        f'<td class="muted">{html.escape(resolved)}</td>'
        f"<td>{detail}</td>"
        "</tr>"
    )


def _fmt(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
