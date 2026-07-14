from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netbackup.storage import record_run
from netbackup.web import app
from netbackup.web_security import generate_csrf_token


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_root = tmp_path / "backups"
    db_path = tmp_path / "netbackup.db"
    config_dir = tmp_path / "config"
    log_dir = tmp_path / "logs"
    backup_root.mkdir()
    config_dir.mkdir()
    log_dir.mkdir()
    inventory_path = config_dir / "devices.yml"
    inventory_path.write_text(
        "devices:\n"
        "  - name: device-a\n"
        "    host: 1.1.1.1\n"
        "    vendor: dummy\n"
        "    method: api\n",
        encoding="utf-8",
    )
    log_path = log_dir / "netbackup.log"
    log_path.write_text("INFO backup complete\n", encoding="utf-8")

    monkeypatch.setattr("netbackup.settings.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.settings.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.settings.BASE_DIR", tmp_path)
    monkeypatch.setattr("netbackup.settings.LOG_FILE", log_path)
    monkeypatch.setattr("netbackup.storage.DB_PATH", db_path)
    monkeypatch.setattr("netbackup.paths.BACKUP_DIR", backup_root)
    monkeypatch.setattr("netbackup.paths.BASE_DIR", tmp_path)
    monkeypatch.setattr("netbackup.paths.LOG_FILE", log_path)
    monkeypatch.setattr("netbackup.web.BASE_DIR", tmp_path)
    monkeypatch.setattr("netbackup.web.LOG_FILE", log_path)
    monkeypatch.setattr("netbackup.web.DEFAULT_INVENTORY_PATH", inventory_path)
    monkeypatch.setattr("netbackup.settings.WEB_AUTH_ENABLED", False)
    monkeypatch.setattr("netbackup.web.WEB_AUTH_ENABLED", False)
    monkeypatch.setattr("netbackup.auth.WEB_AUTH_ENABLED", False)
    monkeypatch.setattr("netbackup.auth.WEB_HOST", "127.0.0.1")
    monkeypatch.setattr("netbackup.auth._NETWORK_EXPOSED", False)
    monkeypatch.delenv("NETBACKUP_INVENTORY", raising=False)
    return TestClient(app), backup_root, inventory_path, log_path


def _csrf_field() -> dict[str, str]:
    return {"csrf_token": generate_csrf_token(), "confirm_write": "yes"}


def test_view_config_serves_file_inside_backup_root(client):
    test_client, backup_root, *_rest = client
    config_path = backup_root / "device-a" / "2026-06-29" / "120000.cfg"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("hostname test", encoding="utf-8")

    record_run("device-a", "1.1.1.1", "dummy", "success", str(config_path), "ok")
    run_id = 1

    response = test_client.get(f"/runs/{run_id}/config")
    assert response.status_code == 200
    assert "hostname test" in response.text


def test_view_config_rejects_path_outside_backup_root(client, tmp_path: Path):
    test_client, _backup_root, *_rest = client
    outside = tmp_path / "outside.cfg"
    outside.write_text("secret", encoding="utf-8")

    record_run("device-a", "1.1.1.1", "dummy", "success", str(outside.resolve()), "ok")

    response = test_client.get("/runs/1/config")
    assert response.status_code == 404


def test_network_exposure_requires_auth(client, monkeypatch: pytest.MonkeyPatch):
    test_client, _backup_root, *_rest = client
    monkeypatch.setattr("netbackup.auth.WEB_AUTH_ENABLED", False)
    monkeypatch.setattr("netbackup.auth.WEB_HOST", "0.0.0.0")
    monkeypatch.setattr("netbackup.auth._NETWORK_EXPOSED", True)
    monkeypatch.setattr("netbackup.web.WEB_AUTH_ENABLED", False)

    response = test_client.get("/config")
    assert response.status_code == 503


def test_web_auth_required_when_enabled(client, monkeypatch: pytest.MonkeyPatch):
    test_client, _backup_root, *_rest = client
    monkeypatch.setattr("netbackup.auth.WEB_AUTH_ENABLED", True)
    monkeypatch.setattr("netbackup.auth.WEB_USERNAME", "admin")
    monkeypatch.setattr("netbackup.auth.WEB_PASSWORD", "secret")
    monkeypatch.setattr("netbackup.web.WEB_AUTH_ENABLED", True)

    unauthenticated = test_client.get("/")
    assert unauthenticated.status_code == 401

    authenticated = test_client.get("/", auth=("admin", "secret"))
    assert authenticated.status_code == 200


def test_backup_now_starts_background_job(client, monkeypatch: pytest.MonkeyPatch):
    test_client, _backup_root, *_rest = client
    calls: list[str] = []

    def fake_execute(inventory_path: str) -> int:
        calls.append(inventory_path)
        return 0

    monkeypatch.setattr("netbackup.jobs._execute_backup", fake_execute)

    response = test_client.post("/backup-now", data=_csrf_field(), follow_redirects=False)
    assert response.status_code == 303
    assert "Backup started" in response.headers["location"]

    import time

    deadline = time.time() + 2
    while time.time() < deadline and not calls:
        time.sleep(0.05)
    assert calls

    job = test_client.get("/api/job").json()
    assert job["status"] in {"completed", "running", "failed"}


def test_backup_now_rejects_missing_csrf_token(client):
    test_client, _backup_root, *_rest = client
    response = test_client.post("/backup-now", follow_redirects=False)
    assert response.status_code == 422


def test_index_shows_localized_timestamp(client, monkeypatch: pytest.MonkeyPatch):
    test_client, _backup_root, *_rest = client
    monkeypatch.setattr(
        "netbackup.web.format_display_timestamp",
        lambda value: "LOCAL-TIME" if value else "",
    )
    record_run("device-a", "1.1.1.1", "dummy", "success", None, "ok")

    response = test_client.get("/")
    assert response.status_code == 200
    assert "LOCAL-TIME" in response.text


def test_index_renders_uniform_action_widgets(client):
    test_client, _backup_root, *_rest = client
    response = test_client.get("/")
    assert response.status_code == 200
    for label in (
        "Backup Now",
        "Open Internal Wiki",
        "View Logs",
        "View Config",
        "Edit Config",
    ):
        assert label in response.text
    assert response.text.count("action-widget") == 5


def test_view_logs_shows_recent_log_content(client):
    test_client, _backup_root, _inventory_path, log_path = client
    log_path.write_text("INFO first line\nERROR second line\n", encoding="utf-8")

    response = test_client.get("/logs")
    assert response.status_code == 200
    assert "ERROR second line" in response.text


def test_view_config_shows_inventory_yaml(client):
    test_client, _backup_root, inventory_path, _log_path = client
    inventory_path.write_text(
        "devices:\n  - name: device-a\n    host: 1.1.1.1\n    vendor: dummy\n    method: api\n",
        encoding="utf-8",
    )

    response = test_client.get("/config")
    assert response.status_code == 200
    assert "device-a" in response.text
    assert "Edit config" in response.text


def test_edit_config_page_renders_textarea(client):
    test_client, _backup_root, inventory_path, _log_path = client
    inventory_path.write_text(
        "devices:\n  - name: device-a\n    host: 1.1.1.1\n    vendor: dummy\n    method: api\n",
        encoding="utf-8",
    )

    response = test_client.get("/config/edit")
    assert response.status_code == 200
    assert 'name="content"' in response.text
    assert 'name="csrf_token"' in response.text
    assert 'name="confirm_write"' in response.text
    assert "Disk write warning" in response.text


def test_save_config_requires_confirm_write(client):
    test_client, _backup_root, inventory_path, _log_path = client
    original = inventory_path.read_text(encoding="utf-8")

    response = test_client.post(
        "/config",
        data={"content": original, **_csrf_field(), "confirm_write": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "confirm the disk write" in response.headers["location"]
    assert inventory_path.read_text(encoding="utf-8") == original


def test_startup_warns_when_production_inventory_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    example_path = tmp_path / "config" / "devices.example.yml"
    example_path.parent.mkdir(parents=True)
    example_path.write_text("devices: []\n", encoding="utf-8")
    production_path = tmp_path / "config" / "devices.yml"

    monkeypatch.setattr("netbackup.web.BASE_DIR", tmp_path)
    monkeypatch.setattr("netbackup.web.DEFAULT_INVENTORY_PATH", production_path)
    monkeypatch.setattr("netbackup.web.EXAMPLE_INVENTORY_PATH", example_path)
    monkeypatch.delenv("NETBACKUP_INVENTORY", raising=False)

    from netbackup.web import _warn_inventory_on_startup

    with caplog.at_level("WARNING"):
        _warn_inventory_on_startup()

    assert "Production inventory file not found" in caplog.text
    assert str(production_path) in caplog.text


def test_index_shows_inventory_warning_when_using_example_fallback(client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_client, _backup_root, inventory_path, _log_path = client
    example_path = tmp_path / "config" / "devices.example.yml"
    example_path.parent.mkdir(parents=True, exist_ok=True)
    example_path.write_text("devices: []\n", encoding="utf-8")
    inventory_path.unlink()

    monkeypatch.setattr("netbackup.web.BASE_DIR", tmp_path)
    monkeypatch.setattr("netbackup.web.DEFAULT_INVENTORY_PATH", inventory_path)
    monkeypatch.setattr("netbackup.web.EXAMPLE_INVENTORY_PATH", example_path)

    response = test_client.get("/")
    assert response.status_code == 200
    assert "Inventory warning" in response.text
    assert "Git pull will not overwrite local config" in response.text


def test_save_config_updates_inventory(client):
    test_client, _backup_root, inventory_path, _log_path = client
    updated = (
        "devices:\n"
        "  - name: device-b\n"
        "    host: 2.2.2.2\n"
        "    vendor: dummy\n"
        "    method: api\n"
    )

    response = test_client.post(
        "/config",
        data={"content": updated, **_csrf_field()},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Config saved successfully" in response.headers["location"]
    assert "device-b" in inventory_path.read_text(encoding="utf-8")
    assert inventory_path.with_suffix(".yml.bak").exists()


def test_save_config_rejects_invalid_yaml(client):
    test_client, _backup_root, inventory_path, _log_path = client
    original = inventory_path.read_text(encoding="utf-8")

    response = test_client.post(
        "/config",
        data={"content": "devices:\n  - name: broken\n", **_csrf_field()},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert inventory_path.read_text(encoding="utf-8") == original


def test_save_config_rejects_invalid_csrf_token(client):
    test_client, _backup_root, inventory_path, _log_path = client
    original = inventory_path.read_text(encoding="utf-8")

    response = test_client.post(
        "/config",
        data={"content": original, "csrf_token": "bad-token"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert inventory_path.read_text(encoding="utf-8") == original


def test_inventory_outside_project_root_is_rejected(client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_client, _backup_root, _inventory_path, _log_path = client
    outside_inventory = tmp_path / "outside" / "devices.yml"
    outside_inventory.parent.mkdir()
    outside_inventory.write_text(
        "devices:\n  - name: device-a\n    host: 1.1.1.1\n    vendor: dummy\n    method: api\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NETBACKUP_INVENTORY", str(outside_inventory))

    response = test_client.get("/config")
    assert response.status_code == 404


def test_security_headers_are_present(client):
    test_client, _backup_root, *_rest = client
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in response.headers


def test_api_runs_limit_is_clamped(client, monkeypatch: pytest.MonkeyPatch):
    test_client, _backup_root, *_rest = client
    monkeypatch.setattr("netbackup.web.latest_runs", lambda limit: [{"id": limit}])

    response = test_client.get("/api/runs?limit=9999")
    assert response.status_code == 200
    assert response.json() == [{"id": 500}]


def test_dashboard_escapes_user_supplied_message(client):
    test_client, _backup_root, *_rest = client
    response = test_client.get("/?message=<script>alert(1)</script>")
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
