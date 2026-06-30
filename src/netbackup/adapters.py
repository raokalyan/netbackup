from __future__ import annotations

import os
from typing import Any
from xml.etree import ElementTree

from .inventory import Device
from .logging_setup import setup_logging
from .settings import device_env_name, resolve_device_secret

logger = setup_logging()

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

SSH_VENDOR_DEFAULTS: dict[str, dict[str, Any]] = {
    "cisco": {"device_type": "cisco_ios", "commands": ["show running-config"]},
    "cisco_ios": {"device_type": "cisco_ios", "commands": ["show running-config"]},
    "cisco_nxos": {"device_type": "cisco_nxos", "commands": ["show running-config"]},
    "juniper": {"device_type": "juniper_junos", "commands": ["show configuration | display set"]},
    "junos": {"device_type": "juniper_junos", "commands": ["show configuration | display set"]},
    "arista": {"device_type": "arista_eos", "commands": ["show running-config"]},
    "generic": {"device_type": "autodetect", "commands": ["show running-config"]},
}


def fetch_config(device: Device) -> str:
    if device.vendor.lower() in {"panos", "panorama"} and device.method.lower() == "api":
        return fetch_panos_config(device)
    if device.method.lower() == "ssh":
        return fetch_ssh_config(device)
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
        label = command.get("name", "custom-command")
        params = {key: value for key, value in command.items() if key != "name"}
        response_text = panos_api_request(device, params)
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
    logger.info("PAN-OS API request for %s (%s)", device.name, params.get("type", "unknown"))
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


def fetch_ssh_config(device: Device) -> str:
    try:
        from netmiko import ConnectHandler
    except ImportError as exc:
        raise BackupError(
            "The ssh adapter requires the 'netmiko' package. Run: pip install -r requirements.txt"
        ) from exc

    username = resolve_device_secret(device.name, "username", device.options.get("username_env"))
    password = resolve_device_secret(device.name, "password", device.options.get("password_env"))
    if not username or not password:
        username_env = device.options.get("username_env") or device_env_name(device.name, "username")
        password_env = device.options.get("password_env") or device_env_name(device.name, "password")
        raise BackupError(
            f"Missing SSH credentials for {device.name}. "
            f"Set {username_env} and {password_env} (or NETBACKUP_DEFAULT_USERNAME/PASSWORD)."
        )

    vendor_key = device.vendor.lower()
    vendor_defaults = SSH_VENDOR_DEFAULTS.get(vendor_key, SSH_VENDOR_DEFAULTS["generic"])
    device_type = str(device.options.get("device_type") or vendor_defaults["device_type"])
    commands = device.options.get("commands") or vendor_defaults["commands"]
    if not isinstance(commands, list) or not commands:
        raise BackupError(f"commands must be a non-empty list for SSH device {device.name}")

    connect_args: dict[str, Any] = {
        "device_type": device_type,
        "host": device.host,
        "username": username,
        "password": password,
        "port": int(device.options.get("port", 22)),
        "timeout": int(device.options.get("timeout", 30)),
        "conn_timeout": int(device.options.get("conn_timeout", 30)),
    }

    enable_secret = resolve_device_secret(
        device.name,
        "enable_password",
        device.options.get("enable_password_env"),
    )
    if enable_secret:
        connect_args["secret"] = enable_secret

    logger.info("SSH backup starting for %s (%s via %s)", device.name, device.host, device_type)
    outputs: list[str] = []
    with ConnectHandler(**connect_args) as connection:
        for command in commands:
            read_timeout = int(device.options.get("read_timeout", 120))
            output = connection.send_command(str(command), read_timeout=read_timeout)
            outputs.append(f"===== {command} =====\n{output.strip()}\n")

    logger.info("SSH backup completed for %s (%s command(s))", device.name, len(commands))
    return "\n".join(outputs)


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
