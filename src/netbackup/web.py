from __future__ import annotations

import os
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .auth import require_web_auth
from .jobs import get_job_state, start_backup_job
from .logging_setup import setup_logging
from .paths import resolve_backup_file
from .settings import BACKUP_DIR, RETENTION_DAYS, WEB_AUTH_ENABLED
from .storage import get_run, latest_runs

logger = setup_logging()

BASE_DIR = Path(__file__).resolve().parents[2]
WIKI_PATH = BASE_DIR / "docs" / "wiki.md"
DEFAULT_INVENTORY_PATH = BASE_DIR / "config" / "devices.yml"
EXAMPLE_INVENTORY_PATH = BASE_DIR / "config" / "devices.example.yml"

app = FastAPI(title="NetBackup", version="0.2.0")


@app.on_event("startup")
def on_startup() -> None:
    if WEB_AUTH_ENABLED:
        logger.info("Web UI authentication enabled")
    else:
        logger.warning(
            "Web UI authentication is disabled. Set NETBACKUP_WEB_USERNAME and "
            "NETBACKUP_WEB_PASSWORD to protect the dashboard."
        )


def _inventory_path() -> Path:
    configured = os.getenv("NETBACKUP_INVENTORY")
    if configured:
        return Path(configured).expanduser()
    if DEFAULT_INVENTORY_PATH.exists():
        return DEFAULT_INVENTORY_PATH
    return EXAMPLE_INVENTORY_PATH


def _backup_links(row: dict) -> str:
    backup_path = row.get("backup_path")
    if row.get("status") != "success" or not backup_path:
        return escape(backup_path or "")
    run_id = row["id"]
    path_text = escape(backup_path)
    return (
        f"{path_text}<br>"
        f'<a href="/runs/{run_id}/config">View</a> '
        f'<a href="/runs/{run_id}/config?download=1">Download</a>'
    )


def _media_type(path: Path) -> str:
    if path.suffix.lower() == ".xml":
        return "application/xml"
    return "text/plain"


def _job_status_html() -> str:
    job = get_job_state()
    if job.status == "idle":
        return ""
    return (
        f"<div class='job-status'>Backup job: <b>{escape(job.status)}</b>"
        f"{f' — {escape(job.message)}' if job.message else ''}"
        f"{f' (started {escape(job.started_at)})' if job.started_at else ''}"
        f"</div>"
    )


@app.get("/", dependencies=[Depends(require_web_auth)])
def index(message: str | None = None) -> HTMLResponse:
    rows = latest_runs(50)
    table_rows = "".join(
        f"<tr><td>{escape(r['created_at'])}</td><td>{escape(r['device_name'])}</td>"
        f"<td>{escape(r['host'])}</td><td>{escape(r['vendor'])}</td>"
        f"<td><b>{escape(r['status'])}</b></td><td>{_backup_links(r)}</td>"
        f"<td>{escape(r.get('message') or '')}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='7' class='empty'>No backup runs yet. Click Backup Now to create one.</td></tr>"
    banner = f"<div class='banner'>{escape(message)}</div>" if message else ""
    inventory = escape(str(_inventory_path().relative_to(BASE_DIR)))
    auth_note = (
        "<div class='muted'>Authentication: enabled</div>"
        if WEB_AUTH_ENABLED
        else "<div class='muted warn'>Authentication: disabled (set NETBACKUP_WEB_USERNAME/PASSWORD)</div>"
    )
    html = f"""
    <html><head><title>NetBackup</title>
      <style>
        body {{ margin: 0; font-family: Arial, sans-serif; background: #f3f6fb; color: #172033; }}
        .wrap {{ max-width: 1150px; margin: 38px auto; padding: 0 24px; }}
        .hero {{ background: linear-gradient(135deg, #0f766e, #2563eb); color: white; padding: 28px; border-radius: 18px; box-shadow: 0 12px 30px #1f293733; }}
        .hero h1 {{ margin: 0 0 8px; font-size: 34px; }}
        .actions {{ display: flex; gap: 12px; align-items: center; margin-top: 22px; flex-wrap: wrap; }}
        button, .linkbtn {{ border: 0; border-radius: 12px; padding: 12px 18px; font-weight: 700; cursor: pointer; text-decoration: none; }}
        button {{ background: #22c55e; color: #06230f; box-shadow: 0 6px 14px #0002; }}
        .linkbtn {{ background: #ffffff22; color: white; border: 1px solid #ffffff55; }}
        .card {{ margin-top: 22px; background: white; border-radius: 18px; padding: 22px; box-shadow: 0 10px 24px #64748b22; }}
        .banner {{ margin-top: 18px; background: #dcfce7; color: #14532d; padding: 12px 14px; border-radius: 12px; font-weight: 700; }}
        .job-status {{ margin-top: 18px; background: #dbeafe; color: #1e3a8a; padding: 12px 14px; border-radius: 12px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th {{ text-align: left; background: #eef2ff; color: #3730a3; }}
        th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
        .empty {{ text-align: center; color: #64748b; padding: 28px; }}
        .muted {{ color: #dbeafe; font-size: 13px; margin-top: 8px; }}
        .warn {{ color: #fde68a; }}
      </style>
    </head>
    <body><div class="wrap">
      <section class="hero">
        <h1>NetBackup</h1>
        <p>Internal dashboard for network config backups.</p>
        <div class="actions">
          <form action="/backup-now" method="post"><button type="submit">Backup Now</button></form>
          <a class="linkbtn" href="/wiki">Open Internal Wiki</a>
        </div>
        <div class="muted">Inventory: {inventory}</div>
        <div class="muted">Retention: {RETENTION_DAYS} days</div>
        {auth_note}
      </section>
      {banner}
      {_job_status_html()}
      <section class="card">
        <h2>Latest backup runs</h2>
        <table>
          <tr><th>Time</th><th>Device</th><th>Host</th><th>Vendor</th><th>Status</th><th>Path</th><th>Message</th></tr>
          {table_rows}
        </table>
      </section>
    </div></body></html>
    """
    return HTMLResponse(html)


@app.post("/backup-now", dependencies=[Depends(require_web_auth)])
def backup_now() -> RedirectResponse:
    inventory = str(_inventory_path())
    job = start_backup_job(inventory)
    if job.status == "busy":
        message = job.message or "A backup is already running"
    else:
        message = "Backup started in the background"
    logger.info("Backup requested from web UI: %s", message)
    return RedirectResponse(f"/?message={quote(message)}", status_code=303)


@app.get("/api/runs", dependencies=[Depends(require_web_auth)])
def api_runs(limit: int = 100) -> list[dict]:
    return latest_runs(limit)


@app.get("/api/job", dependencies=[Depends(require_web_auth)])
def api_job() -> dict:
    job = get_job_state()
    return {
        "status": job.status,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "exit_code": job.exit_code,
        "message": job.message,
        "inventory_path": job.inventory_path,
    }


@app.get("/runs/{run_id}/config", dependencies=[Depends(require_web_auth)])
def view_config(run_id: int, download: bool = False) -> FileResponse:
    run = get_run(run_id)
    if not run or run.get("status") != "success" or not run.get("backup_path"):
        raise HTTPException(status_code=404, detail="Backup config not found")

    try:
        path = resolve_backup_file(run["backup_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup config not found") from None

    return FileResponse(
        path,
        media_type=_media_type(path),
        filename=path.name,
        content_disposition_type="attachment" if download else "inline",
    )


def _render_wiki_markdown(markdown: str) -> str:
    """Render the small internal wiki markdown file without extra dependencies."""
    lines = markdown.splitlines()
    html_parts: list[str] = []
    in_code = False
    in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            if in_code:
                html_parts.append("</code></pre>")
            else:
                html_parts.append("<pre><code>")
            in_code = not in_code
            continue

        if in_code:
            html_parts.append(escape(line) + "\n")
            continue

        if not line:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        if line.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3>{escape(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{escape(line[2:])}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{escape(line)}</p>")

    if in_list:
        html_parts.append("</ul>")
    if in_code:
        html_parts.append("</code></pre>")

    return "\n".join(html_parts)


@app.get("/wiki", dependencies=[Depends(require_web_auth)])
def wiki() -> HTMLResponse:
    if WIKI_PATH.exists():
        body = _render_wiki_markdown(WIKI_PATH.read_text(encoding="utf-8"))
    else:
        body = "<h1>NetBackup Internal Wiki</h1><p>Wiki file not found.</p>"

    html = f"""
    <html>
      <head>
        <title>NetBackup Wiki</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 2rem; max-width: 1100px; line-height: 1.5; }}
          pre {{ background: #f5f5f5; padding: 1rem; overflow-x: auto; }}
          code {{ font-family: Consolas, monospace; }}
          a {{ color: #0645ad; }}
        </style>
      </head>
      <body>
        <p><a href="/">Back to backup dashboard</a></p>
        {body}
      </body>
    </html>
    """
    return HTMLResponse(html)
