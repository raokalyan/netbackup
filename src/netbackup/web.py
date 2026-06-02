from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from html import escape
from urllib.parse import quote
from .backup import run_backup
from .storage import latest_runs

BASE_DIR = Path(__file__).resolve().parents[2]
WIKI_PATH = BASE_DIR / "docs" / "wiki.md"
DEMO_INVENTORY_PATH = BASE_DIR / "config" / "devices.demo.yml"
DEFAULT_INVENTORY_PATH = BASE_DIR / "config" / "devices.yml"

app = FastAPI(title="NetBackup", version="0.1.0")

def _inventory_path() -> Path:
    return DEMO_INVENTORY_PATH if DEMO_INVENTORY_PATH.exists() else DEFAULT_INVENTORY_PATH

@app.get("/")
def index(message: str | None = None) -> HTMLResponse:
    rows = latest_runs(50)
    table_rows = "".join(
        f"<tr><td>{escape(r['created_at'])}</td><td>{escape(r['device_name'])}</td><td>{escape(r['host'])}</td><td>{escape(r['vendor'])}</td><td><b>{escape(r['status'])}</b></td><td>{escape(r.get('backup_path') or '')}</td><td>{escape(r.get('message') or '')}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='7' class='empty'>No backup runs yet. Click Backup Now to create one.</td></tr>"
    banner = f"<div class='banner'>{escape(message)}</div>" if message else ""
    inventory = escape(str(_inventory_path().relative_to(BASE_DIR)))
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
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th {{ text-align: left; background: #eef2ff; color: #3730a3; }}
        th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
        .empty {{ text-align: center; color: #64748b; padding: 28px; }}
        .muted {{ color: #dbeafe; font-size: 13px; margin-top: 8px; }}
      </style>
    </head>
    <body><div class="wrap">
      <section class="hero">
        <h1>NetBackup</h1>
        <p>Local demo dashboard for simple network config backups.</p>
        <div class="actions">
          <form action="/backup-now" method="post"><button type="submit">⚡ Backup Now</button></form>
          <a class="linkbtn" href="/wiki">Open Internal Wiki</a>
        </div>
        <div class="muted">Inventory: {inventory}</div>
      </section>
      {banner}
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

@app.post("/backup-now")
def backup_now() -> RedirectResponse:
    code = run_backup(str(_inventory_path()))
    message = "Backup completed" if code == 0 else "Backup finished with errors"
    return RedirectResponse(f"/?message={quote(message)}", status_code=303)

@app.get("/api/runs")
def api_runs(limit: int = 100) -> list[dict]:
    return latest_runs(limit)



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


@app.get("/wiki")
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
