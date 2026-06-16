from __future__ import annotations
import os
from typing import Any
from xml.etree import ElementTree
from .inventory import Device
from .settings import device_env_name, resolve_device_secret

class BackupError(RuntimeError):
    pass

PANORAMA_COMMAND_ALIASES: dict[str, dict[str, str]] = {
    "system-info": {"type": "op", "cmd": "<show><system><info></info></system></show>"},
    "panorama-status": {"type": "op", "cmd": "<show><panorama-status></panorama-status></show>"},
    "connected-devices": {"type": "op", "cmd": "<show><devices><connected></connected></devices></show>"},
    "managed-devices": {
        "type": "config",
        "action": "show",
        "xpath": "/config/devices/entry[@name='localhost.localdomain']/devices",
    },
    "device-groups": {
        "type": "config",
        "action": "show",
        "xpath": "/config/devices/entry[@name='localhost.localdomain']/device-group",
    },
    "templates": {
        "type": "config",
        "action": "show",
        "xpath": "/config/devices/entry[@name='localhost.localdomain']/template",
    },
    "template-stacks": {
        "type": "config",
        "action": "show",
        "xpath": "/config/devices/entry[@name='localhost.localdomain']/template-stack",
    },
    "plugins": {
        "type": "config",
        "action": "show",
        "xpath": "/config/devices/entry[@name='localhost.localdomain']/plugins",
    },
    "full-config": {"type": "config", "action": "show"},
    "export-config": {"type": "export", "category": "configuration"},
}

def fetch_config(device: Device) -> str:
    if device.vendor.lower() in {"panos", "panorama"} and device.method.lower() == "api":
        return fetch_panos_config(device)
    if device.method.lower() == "dummy":
        return dummy_config(device)
    if device.method.lower() == "placeholder":
        return placeholder_config(device)
    raise BackupError(f"Unsupported device adapter: vendor={device.vendor} method={device.method}")

def fetch_panos_config(device: Device) -> str:
    commands = device.options.get("commands")
    if commands:
        return fetch_panos_commands(device, commands)
    return fetch_panos_exported_config(device)

def fetch_panos_exported_config(device: Device) -> str:
    return panos_api_request(device, {"type": "export", "category": "configuration"})

def fetch_panos_commands(device: Device, commands: Any) -> str:
    if not isinstance(commands, list):
        raise BackupError(f"commands must be a list for {device.name}")

    normalized_commands = [normalize_panos_command(raw_command) for raw_command in commands]
    if len(normalized_commands) == 1 and is_panos_export_config_request(normalized_commands[0]):
        command = {k: v for k, v in normalized_commands[0].items() if k != "name"}
        return panos_api_request(device, command)

    outputs: list[str] = []
    for command in normalized_commands:
        label = command.pop("name")
        response_text = panos_api_request(device, command)
        outputs.append(f"===== {label} =====\n{response_text.strip()}\n")
    return "\n".join(outputs)

def is_panos_export_config_request(command: dict[str, str]) -> bool:
    return command.get("type") == "export" and command.get("category") == "configuration"

def normalize_panos_command(raw_command: Any) -> dict[str, str]:
    if isinstance(raw_command, str):
        if raw_command not in PANORAMA_COMMAND_ALIASES:
            known = ", ".join(sorted(PANORAMA_COMMAND_ALIASES))
            raise BackupError(f"Unknown PAN-OS command alias '{raw_command}'. Known aliases: {known}")
        return {"name": raw_command, **PANORAMA_COMMAND_ALIASES[raw_command]}

    if not isinstance(raw_command, dict):
        raise BackupError(f"Invalid PAN-OS command entry: {raw_command!r}")

    name = str(raw_command.get("name") or raw_command.get("alias") or "custom-command")
    if raw_command.get("alias"):
        alias = raw_command["alias"]
        if alias not in PANORAMA_COMMAND_ALIASES:
            known = ", ".join(sorted(PANORAMA_COMMAND_ALIASES))
            raise BackupError(f"Unknown PAN-OS command alias '{alias}'. Known aliases: {known}")
        command = {"name": name, **PANORAMA_COMMAND_ALIASES[alias]}
        command.update({k: str(v) for k, v in raw_command.items() if k not in {"name", "alias"}})
        return command

    if raw_command.get("xpath"):
        return {
            "name": name,
            "type": str(raw_command.get("type", "config")),
            "action": str(raw_command.get("action", "show")),
            "xpath": str(raw_command["xpath"]),
        }

    if raw_command.get("cmd"):
        return {"name": name, "type": str(raw_command.get("type", "op")), "cmd": str(raw_command["cmd"])}

    raise BackupError(f"PAN-OS command entry needs alias, xpath, or cmd: {raw_command!r}")

def panos_api_request(device: Device, params: dict[str, str]) -> str:
    try:
        import requests
    except ImportError as exc:
        raise BackupError("The panos API adapter requires the 'requests' package. Run: pip install -r requirements.txt") from exc

    api_key = resolve_device_secret(device.name, "api_key", device.options.get("api_key_env"))
    if not api_key:
        api_key_env = device.options.get("api_key_env")
        expected = f"{device_env_name(device.name, 'api_key')} (or NETBACKUP_DEFAULT_API_KEY)"
        raise BackupError(
            f"Missing API key for {device.name}. "
            f"Set {api_key_env or expected} environment variable."
        )
    verify_ssl = bool(device.options.get("verify_ssl", True))
    url = f"https://{device.host}/api/"
    response = requests.get(
        url,
        params={**params, "key": api_key},
        timeout=int(device.options.get("timeout", 30)),
        verify=verify_ssl,
    )
    response.raise_for_status()
    raise_for_panos_api_error(response.text)
    return response.text

def raise_for_panos_api_error(response_text: str) -> None:
    try:
        root = ElementTree.fromstring(response_text)
    except ElementTree.ParseError:
        return
    if root.tag != "response" or root.attrib.get("status") != "error":
        return
    message = root.findtext("./msg/line") or root.findtext("./msg") or response_text
    code = root.attrib.get("code", "unknown")
    raise BackupError(f"PAN-OS API error {code}: {message}")

def dummy_config(device: Device) -> str:
    hostname = device.options.get("hostname", device.name)
    site = device.options.get("site", "local-demo")
    interface = device.options.get("interface", "loopback0")
    return (
        f"! Dummy network device config backup\n"
        f"! No real network connection was made\n"
        f"hostname {hostname}\n"
        f"! device_name: {device.name}\n"
        f"! management_ip: {device.host}\n"
        f"! site: {site}\n"
        f"interface {interface}\n"
        f" description Local demo interface\n"
        f" ip address 192.0.2.1 255.255.255.255\n"
        f"! end\n"
    )


def placeholder_config(device: Device) -> str:
    username = resolve_device_secret(device.name, "username", device.options.get("username_env"))
    password_set = resolve_device_secret(device.name, "password", device.options.get("password_env")) is not None
    username_env = device.options.get("username_env") or device_env_name(device.name, "username")
    password_env = device.options.get("password_env") or device_env_name(device.name, "password")
    return (
        f"# Placeholder backup for {device.name} ({device.host})\n"
        f"# Add a real adapter for vendor={device.vendor}.\n"
        f"# Username env: {username_env} = {username or '(not set)'}\n"
        f"# Password env: {password_env} (set: {password_set})\n"
    )
