from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netbackup.storage import record_run
from netbackup.web import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_root = tmp_path / "backups"
    db_path = tmp_path / "netbackup.db"
    backup_root.mkdir()
    monkeypatch.setattr("netbackup.settings.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.settings.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.storage.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.paths.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.settings.WEB_AUTH_ENABLED", False)
    monkeypatch.setattr("netbackup.web.WEB_AUTH_ENABLED", False)
    return TestClient(app), backup_root


def test_view_config_serves_file_inside_backup_root(client):
    test_client, backup_root = client
    config_path = backup_root / "device-a" / "2026-06-29" / "120000.cfg"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("hostname test", encoding="utf-8")

    record_run("device-a", "1.1.1.1", "dummy", "success", str(config_path), "ok")
    run_id = 1

    response = test_client.get(f"/runs/{run_id}/config")
    assert response.status_code == 200
    assert "hostname test" in response.text


def test_view_config_rejects_path_outside_backup_root(client, tmp_path: Path):
    test_client, _backup_root = client
    outside = tmp_path / "outside.cfg"
    outside.write_text("secret", encoding="utf-8")

    record_run("device-a", "1.1.1.1", "dummy", "success", str(outside.resolve()), "ok")

    response = test_client.get("/runs/1/config")
    assert response.status_code == 404


def test_web_auth_required_when_enabled(client, monkeypatch: pytest.MonkeyPatch):
    test_client, _backup_root = client
    monkeypatch.setattr("netbackup.auth.WEB_AUTH_ENABLED", True)
    monkeypatch.setattr("netbackup.auth.WEB_USERNAME", "admin")
    monkeypatch.setattr("netbackup.auth.WEB_PASSWORD", "secret")
    monkeypatch.setattr("netbackup.web.WEB_AUTH_ENABLED", True)

    unauthenticated = test_client.get("/")
    assert unauthenticated.status_code == 401

    authenticated = test_client.get("/", auth=("admin", "secret"))
    assert authenticated.status_code == 200


def test_backup_now_starts_background_job(client, monkeypatch: pytest.MonkeyPatch):
    test_client, _backup_root = client
    calls: list[str] = []

    def fake_execute(inventory_path: str) -> int:
        calls.append(inventory_path)
        return 0

    monkeypatch.setattr("netbackup.jobs._execute_backup", fake_execute)

    response = test_client.post("/backup-now", follow_redirects=False)
    assert response.status_code == 303
    assert "Backup started" in response.headers["location"]

    import time

    deadline = time.time() + 2
    while time.time() < deadline and not calls:
        time.sleep(0.05)
    assert calls

    job = test_client.get("/api/job").json()
    assert job["status"] in {"completed", "running", "failed"}
