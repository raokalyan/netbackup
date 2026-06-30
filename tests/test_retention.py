from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from netbackup.retention import apply_retention
from netbackup.storage import connect, record_run


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_root = tmp_path / "backups"
    db_path = tmp_path / "netbackup.db"
    backup_root.mkdir()
    monkeypatch.setattr("netbackup.retention.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.settings.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.settings.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.storage.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.settings.RETENTION_DAYS", 30)
    monkeypatch.setattr("netbackup.retention.RETENTION_DAYS", 30)
    return {"backup_root": backup_root, "db_path": db_path}


def test_retention_deletes_old_files_and_rows(isolated_env):
    backup_root = isolated_env["backup_root"]
    old_file = backup_root / "device-a" / "2020-01-01" / "old.cfg"
    new_file = backup_root / "device-a" / "2099-01-01" / "new.cfg"
    old_file.parent.mkdir(parents=True)
    new_file.parent.mkdir(parents=True)
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")

    old_time = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
    new_time = datetime.now(timezone.utc).timestamp()
    import os

    os.utime(old_file, (old_time, old_time))
    os.utime(new_file, (new_time, new_time))

    old_created = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    new_created = datetime.now(timezone.utc).isoformat()
    with connect(isolated_env["db_path"]) as conn:
        conn.execute(
            "INSERT INTO backup_runs (device_name, host, vendor, status, backup_path, message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("device-a", "1.1.1.1", "dummy", "success", str(old_file), "old", old_created),
        )
        conn.execute(
            "INSERT INTO backup_runs (device_name, host, vendor, status, backup_path, message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("device-a", "1.1.1.1", "dummy", "success", str(new_file), "new", new_created),
        )

    files_deleted, rows_deleted = apply_retention(backup_root=backup_root, retention_days=30)
    assert files_deleted == 1
    assert rows_deleted == 1
    assert not old_file.exists()
    assert new_file.exists()

    with connect(isolated_env["db_path"]) as conn:
        rows = conn.execute("SELECT message FROM backup_runs").fetchall()
    assert [row["message"] for row in rows] == ["new"]
