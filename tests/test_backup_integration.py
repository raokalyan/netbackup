from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from netbackup import backup as backup_module
from netbackup.backup import BackupBusyError, _execute_backup, run_backup, safe_name, write_backup
from netbackup.inventory import Device
from netbackup.storage import latest_runs


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_root = tmp_path / "backups"
    db_path = tmp_path / "netbackup.db"
    log_file = tmp_path / "logs" / "netbackup.log"
    monkeypatch.setattr("netbackup.backup.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.retention.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.settings.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.settings.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.storage.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.settings.LOG_FILE", log_file)
    monkeypatch.setattr("netbackup.logging_setup.LOG_FILE", log_file)
    return {"backup_root": backup_root, "db_path": db_path}


def test_run_dummy_backup_creates_file_and_db_record(isolated_env, tmp_path: Path):
    inventory = tmp_path / "devices.demo.yml"
    inventory.write_text(
        """
devices:
  - name: demo-router-01
    host: 127.0.0.1
    vendor: dummy
    method: dummy
    hostname: demo-router-01
""",
        encoding="utf-8",
    )

    exit_code = _execute_backup(str(inventory))
    assert exit_code == 0

    backup_root = isolated_env["backup_root"]
    device_dir = backup_root / safe_name("demo-router-01")
    backup_files = list(device_dir.rglob("*.cfg"))
    assert len(backup_files) == 1
    assert "hostname demo-router-01" in backup_files[0].read_text(encoding="utf-8")

    runs = latest_runs()
    assert len(runs) == 1
    assert runs[0]["device_name"] == "demo-router-01"
    assert runs[0]["status"] == "success"
    assert runs[0]["backup_path"] == str(backup_files[0])


def test_write_backup_uses_utc_date_directory(isolated_env):
    device = Device("demo-router-01", "127.0.0.1", "dummy", "dummy", {})
    path = write_backup(device, "config", backup_root=isolated_env["backup_root"])
    assert path.parent.parent.name == "demo-router-01"
    assert len(path.parent.name.split("-")) == 3


def test_run_backup_skip_if_busy_raises_when_lock_held(isolated_env, tmp_path: Path):
    inventory = tmp_path / "devices.demo.yml"
    inventory.write_text(
        """
devices:
  - name: demo-router-01
    host: 127.0.0.1
    vendor: dummy
    method: dummy
""",
        encoding="utf-8",
    )

    assert backup_module._backup_lock.acquire(blocking=False)
    try:
        with pytest.raises(BackupBusyError):
            run_backup(str(inventory), skip_if_busy=True)
    finally:
        backup_module._backup_lock.release()
