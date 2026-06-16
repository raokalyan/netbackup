import pytest

from netbackup.adapters import BackupError, normalize_panos_command


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
