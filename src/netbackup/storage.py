from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .settings import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS backup_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT NOT NULL,
    host TEXT NOT NULL,
    vendor TEXT NOT NULL,
    status TEXT NOT NULL,
    backup_path TEXT,
    message TEXT,
    created_at TEXT NOT NULL
);
"""

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def record_run(device_name: str, host: str, vendor: str, status: str, backup_path: str | None, message: str | None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO backup_runs (device_name, host, vendor, status, backup_path, message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (device_name, host, vendor, status, backup_path, message, datetime.now(timezone.utc).isoformat()),
        )

def latest_runs(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM backup_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM backup_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None
