import sys
import types

import pytest

from netbackup.adapters import BackupError, fetch_ssh_config
from netbackup.inventory import Device


def test_fetch_ssh_config_runs_commands(monkeypatch):
    captured: dict = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def send_command(self, command, read_timeout=120):
            captured.setdefault("commands", []).append(command)
            return f"output for {command}"

    def fake_connect_handler(**kwargs):
        captured["connect_args"] = kwargs
        return FakeConnection()

    fake_netmiko = types.SimpleNamespace(ConnectHandler=fake_connect_handler)
    monkeypatch.setitem(sys.modules, "netmiko", fake_netmiko)
    monkeypatch.setenv("SWITCH_01_USERNAME", "admin")
    monkeypatch.setenv("SWITCH_01_PASSWORD", "pass")

    device = Device(
        "switch-01",
        "192.0.2.20",
        "cisco",
        "ssh",
        {"device_type": "cisco_ios", "commands": ["show running-config"]},
    )

    output = fetch_ssh_config(device)
    assert captured["connect_args"]["host"] == "192.0.2.20"
    assert captured["commands"] == ["show running-config"]
    assert "output for show running-config" in output


def test_fetch_ssh_config_requires_credentials(monkeypatch):
    fake_netmiko = types.SimpleNamespace(ConnectHandler=lambda **kwargs: None)
    monkeypatch.setitem(sys.modules, "netmiko", fake_netmiko)
    monkeypatch.delenv("SWITCH_01_USERNAME", raising=False)
    monkeypatch.delenv("SWITCH_01_PASSWORD", raising=False)
    monkeypatch.delenv("NETBACKUP_DEFAULT_USERNAME", raising=False)
    monkeypatch.delenv("NETBACKUP_DEFAULT_PASSWORD", raising=False)

    device = Device("switch-01", "192.0.2.20", "cisco", "ssh", {})
    with pytest.raises(BackupError, match="Missing SSH credentials"):
        fetch_ssh_config(device)
