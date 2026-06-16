import pytest

from netbackup.adapters import BackupError, fetch_panos_commands, normalize_panos_command
from netbackup.backup import backup_extension
from netbackup.inventory import Device


def test_normalize_panoroma_alias_command():
    command = normalize_panos_command("device-groups")

    assert command["name"] == "device-groups"
    assert command["type"] == "config"
    assert command["action"] == "show"
    assert "device-group" in command["xpath"]


def test_normalize_custom_op_command():
    command = normalize_panos_command({"name": "jobs", "type": "op", "cmd": "<show><jobs><all></all></jobs></show>"})

    assert command == {
        "name": "jobs",
        "type": "op",
        "cmd": "<show><jobs><all></all></jobs></show>",
    }


def test_unknown_alias_raises_helpful_error():
    with pytest.raises(BackupError, match="Unknown PAN-OS command alias"):
        normalize_panos_command("not-real")


def test_export_config_alias_uses_panorama_export_api():
    command = normalize_panos_command("export-config")

    assert command == {
        "name": "export-config",
        "type": "export",
        "category": "configuration",
    }


def test_panos_default_backup_extension_is_xml_without_commands():
    device = Device("panorama-01", "192.0.2.10", "panorama", "api", {})

    assert backup_extension(device) == ".xml"


def test_panos_command_backup_extension_stays_cfg():
    device = Device("panorama-01", "192.0.2.10", "panorama", "api", {"commands": ["system-info"]})

    assert backup_extension(device) == ".cfg"


def test_single_export_config_command_returns_raw_xml_without_header(monkeypatch):
    calls = []

    def fake_request(device, params):
        calls.append(params)
        return "<config></config>"

    monkeypatch.setattr("netbackup.adapters.panos_api_request", fake_request)
    device = Device("panorama-01", "192.0.2.10", "panorama", "api", {})

    assert fetch_panos_commands(device, ["export-config"]) == "<config></config>"
    assert calls == [{"type": "export", "category": "configuration"}]


def test_panos_export_config_command_extension_is_xml():
    device = Device("panorama-01", "192.0.2.10", "panorama", "api", {"commands": ["export-config"]})

    assert backup_extension(device) == ".xml"
