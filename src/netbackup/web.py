from __future__ import annotations

import os
import tempfile
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .auth import require_web_auth
from .inventory import load_inventory
from .jobs import get_job_state, start_backup_job
from .logging_setup import setup_logging
from .paths import resolve_backup_file, resolve_inventory_file, resolve_log_file
from .settings import (
    BASE_DIR,
    DISPLAY_TIMEZONE,
    LOG_FILE,
    RETENTION_DAYS,
    WEB_AUTH_ENABLED,
    WEB_HOST,
    WEB_PORT,
)
from .storage import get_run, latest_runs
from .timefmt import format_display_timestamp
from .web_security import (
    SecurityHeadersMiddleware,
    clamp_api_limit,
    enforce_rate_limit,
    generate_csrf_token,
    read_tail_bytes,
    validate_config_content,
    validate_csrf_token,
)

logger = setup_logging()

DEFAULT_INVENTORY_PATH = BASE_DIR / "config" / "devices.yml"
EXAMPLE_INVENTORY_PATH = BASE_DIR / "config" / "devices.example.yml"
WIKI_PATH = BASE_DIR / "docs" / "wiki.md"

app = FastAPI(title="NetBackup", version="0.2.0")
app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
def on_startup() -> None:
    network_bind = WEB_HOST in {"0.0.0.0", "::"}
    logger.info("Web UI configured for %s:%s", WEB_HOST, WEB_PORT)
    if WEB_AUTH_ENABLED:
        logger.info("Web UI authentication enabled")
    elif network_bind:
        logger.warning(
            "Web UI is exposed on all network interfaces (%s:%s) without authentication. "
            "Set NETBACKUP_WEB_USERNAME and NETBACKUP_WEB_PASSWORD in .env.",
            WEB_HOST,
            WEB_PORT,
        )
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


def _safe_inventory_display(path: Path) -> str:
    resolved = path.resolve()
    try:
        return escape(str(resolved.relative_to(BASE_DIR.resolve())))
    except ValueError:
        return escape(str(resolved))


def _shared_styles() -> str:
    return """
        :root {
          --bg: #f3f6fb;
          --text: #172033;
          --card: #ffffff;
          --accent: #2563eb;
          --accent-dark: #0f766e;
          --success: #16a34a;
          --border: #dbe3f0;
          --muted: #64748b;
        }
        * { box-sizing: border-box; }
        body {
          margin: 0;
          font-family: "Segoe UI", Arial, sans-serif;
          background: var(--bg);
          color: var(--text);
          line-height: 1.5;
        }
        .wrap { max-width: 1180px; margin: 36px auto; padding: 0 24px 48px; }
        .hero {
          background: linear-gradient(135deg, var(--accent-dark), var(--accent));
          color: white;
          padding: 30px;
          border-radius: 20px;
          box-shadow: 0 16px 36px #1f293733;
        }
        .hero h1 { margin: 0 0 8px; font-size: 34px; letter-spacing: -0.02em; }
        .hero p { margin: 0; opacity: 0.95; }
        .meta { display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 18px; font-size: 13px; opacity: 0.92; }
        .meta span { background: #ffffff22; border: 1px solid #ffffff44; border-radius: 999px; padding: 4px 10px; }
        .warn-pill { color: #fde68a; border-color: #fde68a66 !important; }
        .action-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
          gap: 14px;
          margin-top: 24px;
        }
        .action-widget {
          display: flex;
          flex-direction: column;
          gap: 8px;
          min-height: 132px;
          padding: 16px;
          border-radius: 16px;
          background: #ffffff18;
          border: 1px solid #ffffff44;
          color: white;
          text-decoration: none;
          transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
        }
        .action-widget:hover {
          transform: translateY(-2px);
          background: #ffffff28;
          box-shadow: 0 10px 24px #00000022;
        }
        .action-widget h3 { margin: 0; font-size: 16px; }
        .action-widget p { margin: 0; font-size: 13px; opacity: 0.9; flex: 1; }
        .action-widget .cta {
          align-self: flex-start;
          border-radius: 999px;
          padding: 7px 12px;
          font-size: 12px;
          font-weight: 700;
          background: #ffffff;
          color: #0f4c81;
        }
        form.action-widget { margin: 0; }
        form.action-widget button {
          align-self: flex-start;
          border: 0;
          border-radius: 999px;
          padding: 7px 12px;
          font-size: 12px;
          font-weight: 700;
          background: #ffffff;
          color: #0f4c81;
          cursor: pointer;
        }
        .card {
          margin-top: 22px;
          background: var(--card);
          border-radius: 18px;
          padding: 22px;
          box-shadow: 0 10px 24px #64748b22;
          border: 1px solid var(--border);
        }
        .card h2 { margin: 0 0 14px; font-size: 20px; }
        .banner {
          margin-top: 18px;
          background: #dcfce7;
          color: #14532d;
          padding: 12px 14px;
          border-radius: 12px;
          font-weight: 700;
          border: 1px solid #86efac;
        }
        .banner.error {
          background: #fee2e2;
          color: #991b1b;
          border-color: #fca5a5;
        }
        .job-status {
          margin-top: 18px;
          background: #dbeafe;
          color: #1e3a8a;
          padding: 12px 14px;
          border-radius: 12px;
          border: 1px solid #93c5fd;
        }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { text-align: left; background: #eef2ff; color: #3730a3; }
        th, td { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
        .empty { text-align: center; color: var(--muted); padding: 28px; }
        .toolbar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
        .btn, .btn-secondary {
          display: inline-block;
          border-radius: 10px;
          padding: 10px 14px;
          font-weight: 700;
          text-decoration: none;
          border: 0;
          cursor: pointer;
        }
        .btn { background: var(--success); color: white; }
        .btn-secondary { background: #e2e8f0; color: #1e293b; }
        .code-panel {
          background: #0f172a;
          color: #e2e8f0;
          border-radius: 12px;
          padding: 16px;
          overflow-x: auto;
          font-family: Consolas, "Courier New", monospace;
          font-size: 13px;
          line-height: 1.45;
          white-space: pre-wrap;
          word-break: break-word;
          max-height: 70vh;
        }
        .editor {
          width: 100%;
          min-height: 420px;
          border-radius: 12px;
          border: 1px solid var(--border);
          padding: 14px;
          font-family: Consolas, "Courier New", monospace;
          font-size: 13px;
          line-height: 1.45;
          resize: vertical;
        }
        .back-link { margin-bottom: 18px; }
        .back-link a { color: var(--accent); text-decoration: none; font-weight: 600; }
        .muted-note { color: var(--muted); font-size: 13px; margin-top: 8px; }
    """


def _page_shell(title: str, body: str, *, show_back: bool = True) -> str:
    back_link = '<p class="back-link"><a href="/">← Back to dashboard</a></p>' if show_back else ""
    return f"""
    <html>
      <head>
        <title>{escape(title)}</title>
        <style>{_shared_styles()}</style>
      </head>
      <body>
        <div class="wrap">
          {back_link}
          {body}
        </div>
      </body>
    </html>
    """


def _action_widgets(csrf_token: str) -> str:
    return f"""
      <div class="action-grid">
        <form class="action-widget" action="/backup-now" method="post">
          <h3>Backup Now</h3>
          <p>Run an on-demand backup using the current inventory.</p>
          <input type="hidden" name="csrf_token" value="{escape(csrf_token)}">
          <button type="submit" class="cta">Start backup</button>
        </form>
        <a class="action-widget" href="/wiki">
          <h3>Open Internal Wiki</h3>
          <p>Read operational notes, setup steps, and troubleshooting guides.</p>
          <span class="cta">Open wiki</span>
        </a>
        <a class="action-widget" href="/logs">
          <h3>View Logs</h3>
          <p>Inspect recent application activity and backup job output.</p>
          <span class="cta">View logs</span>
        </a>
        <a class="action-widget" href="/config">
          <h3>View Config</h3>
          <p>Review the active device inventory YAML used for backups.</p>
          <span class="cta">View config</span>
        </a>
        <a class="action-widget" href="/config/edit">
          <h3>Edit Config</h3>
          <p>Update inventory entries with validation before saving changes.</p>
          <span class="cta">Edit config</span>
        </a>
      </div>
    """


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
        f"{f' (started {escape(format_display_timestamp(job.started_at))})' if job.started_at else ''}"
        f"</div>"
    )


def _banner(message: str | None, *, error: bool = False) -> str:
    if not message:
        return ""
    css_class = "banner error" if error else "banner"
    return f"<div class='{css_class}'>{escape(message)}</div>"


def _resolved_inventory() -> Path:
    try:
        return resolve_inventory_file(_inventory_path(), BASE_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Inventory config not found") from exc


@app.get("/", dependencies=[Depends(require_web_auth)])
def index(message: str | None = None, error: str | None = None) -> HTMLResponse:
    rows = latest_runs(50)
    table_rows = "".join(
        f"<tr><td>{escape(format_display_timestamp(r['created_at']))}</td><td>{escape(r['device_name'])}</td>"
        f"<td>{escape(r['host'])}</td><td>{escape(r['vendor'])}</td>"
        f"<td><b>{escape(r['status'])}</b></td><td>{_backup_links(r)}</td>"
        f"<td>{escape(r.get('message') or '')}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='7' class='empty'>No backup runs yet. Click Backup Now to create one.</td></tr>"

    inventory = _safe_inventory_display(_inventory_path())
    auth_note = (
        "<span>Authentication: enabled</span>"
        if WEB_AUTH_ENABLED
        else "<span class='warn-pill'>Authentication: disabled</span>"
    )
    csrf_token = generate_csrf_token()
    body = f"""
      <section class="hero">
        <h1>NetBackup</h1>
        <p>Internal dashboard for network configuration backups.</p>
        {_action_widgets(csrf_token)}
        <div class="meta">
          <span>Inventory: {inventory}</span>
          <span>Retention: {RETENTION_DAYS} days</span>
          <span>Timezone: {escape(str(DISPLAY_TIMEZONE))}</span>
          {auth_note}
        </div>
      </section>
      {_banner(message)}
      {_banner(error, error=True)}
      {_job_status_html()}
      <section class="card">
        <h2>Latest backup runs</h2>
        <table>
          <tr><th>Time</th><th>Device</th><th>Host</th><th>Vendor</th><th>Status</th><th>Path</th><th>Message</th></tr>
          {table_rows}
        </table>
      </section>
    """
    return HTMLResponse(_page_shell("NetBackup", body, show_back=False))


@app.post("/backup-now", dependencies=[Depends(require_web_auth)])
def backup_now(
    request: Request,
    csrf_token: str = Form(...),
) -> RedirectResponse:
    validate_csrf_token(csrf_token)
    enforce_rate_limit(request, scope="backup-now", max_requests=6, window_seconds=60)

    inventory = str(_resolved_inventory())
    job = start_backup_job(inventory)
    if job.status == "busy":
        message = job.message or "A backup is already running"
    else:
        message = "Backup started in the background"
    logger.info("Backup requested from web UI: %s", message)
    return RedirectResponse(f"/?message={quote(message)}", status_code=303)


@app.get("/logs", dependencies=[Depends(require_web_auth)])
def view_logs() -> HTMLResponse:
    try:
        log_path = resolve_log_file(LOG_FILE, BASE_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Log file not found") from exc

    content = escape(read_tail_bytes(str(log_path)))
    body = f"""
      <section class="card">
        <h2>Application logs</h2>
        <p class="muted-note">Showing the most recent portion of <code>{escape(str(log_path))}</code>.</p>
        <div class="code-panel">{content}</div>
      </section>
    """
    return HTMLResponse(_page_shell("NetBackup Logs", body))


@app.get("/config", dependencies=[Depends(require_web_auth)])
def view_inventory_config() -> HTMLResponse:
    inventory_path = _resolved_inventory()
    content = escape(inventory_path.read_text(encoding="utf-8"))
    body = f"""
      <section class="card">
        <div class="toolbar">
          <h2 style="margin:0; flex:1;">Device inventory</h2>
          <a class="btn-secondary" href="/config/edit">Edit config</a>
        </div>
        <p class="muted-note">Active inventory file: <code>{escape(str(inventory_path))}</code></p>
        <div class="code-panel">{content}</div>
      </section>
    """
    return HTMLResponse(_page_shell("NetBackup Config", body))


@app.get("/config/edit", dependencies=[Depends(require_web_auth)])
def edit_inventory_config(message: str | None = None, error: str | None = None) -> HTMLResponse:
    inventory_path = _resolved_inventory()
    content = escape(inventory_path.read_text(encoding="utf-8"))
    csrf_token = generate_csrf_token()
    body = f"""
      <section class="card">
        <h2>Edit device inventory</h2>
        <p class="muted-note">Changes are validated before being saved to <code>{escape(str(inventory_path))}</code>.</p>
        {_banner(message)}
        {_banner(error, error=True)}
        <form action="/config" method="post">
          <input type="hidden" name="csrf_token" value="{escape(csrf_token)}">
          <textarea class="editor" name="content" spellcheck="false">{content}</textarea>
          <div class="toolbar" style="margin-top:14px;">
            <button class="btn" type="submit">Save config</button>
            <a class="btn-secondary" href="/config">Cancel</a>
          </div>
        </form>
      </section>
    """
    return HTMLResponse(_page_shell("Edit NetBackup Config", body))


@app.post("/config", dependencies=[Depends(require_web_auth)])
def save_inventory_config(
    request: Request,
    csrf_token: str = Form(...),
    content: str = Form(...),
) -> RedirectResponse:
    validate_csrf_token(csrf_token)
    enforce_rate_limit(request, scope="save-config", max_requests=10, window_seconds=60)
    validate_config_content(content)

    inventory_path = _resolved_inventory()
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=inventory_path.parent) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        load_inventory(temp_path)
    except ValueError as exc:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        return RedirectResponse(f"/config/edit?error={quote(str(exc))}", status_code=303)
    except Exception:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        logger.exception("Failed to validate inventory config")
        return RedirectResponse(
            f"/config/edit?error={quote('Invalid inventory YAML')}",
            status_code=303,
        )

    backup_path = inventory_path.with_suffix(inventory_path.suffix + ".bak")
    try:
        if inventory_path.exists():
            backup_path.write_text(inventory_path.read_text(encoding="utf-8"), encoding="utf-8")
        if temp_path is None:
            raise HTTPException(status_code=500, detail="Failed to save config")
        temp_path.replace(inventory_path)
    except OSError as exc:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        logger.exception("Failed to save inventory config")
        raise HTTPException(status_code=500, detail="Failed to save config") from exc

    logger.info("Inventory config updated from web UI: %s", inventory_path)
    return RedirectResponse(f"/config/edit?message={quote('Config saved successfully')}", status_code=303)


@app.get("/api/runs", dependencies=[Depends(require_web_auth)])
def api_runs(limit: int = 100) -> list[dict]:
    return latest_runs(clamp_api_limit(limit))


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

    html = _page_shell(
        "NetBackup Wiki",
        f'<section class="card">{body}</section>',
    )
    return HTMLResponse(html)
