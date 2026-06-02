from __future__ import annotations
import os
from .inventory import Device

class BackupError(RuntimeError):
    pass

def fetch_config(device: Device) -> str:
    if device.vendor.lower() == "panos" and device.method.lower() == "api":
        return fetch_panos_config(device)
    if device.method.lower() == "dummy":
        return dummy_config(device)
    if device.method.lower() == "placeholder":
        return placeholder_config(device)
    raise BackupError(f"Unsupported device adapter: vendor={device.vendor} method={device.method}")

def fetch_panos_config(device: Device) -> str:
    try:
        import requests
    except ImportError as exc:
        raise BackupError("The panos API adapter requires the 'requests' package. Run: pip install -r requirements.txt") from exc

    api_key_env = device.options.get("api_key_env")
    api_key = os.getenv(api_key_env or "")
    if not api_key:
        raise BackupError(f"Missing API key environment variable: {api_key_env}")
    verify_ssl = bool(device.options.get("verify_ssl", True))
    url = f"https://{device.host}/api/"
    response = requests.get(
        url,
        params={"type": "config", "action": "show", "key": api_key},
        timeout=30,
        verify=verify_ssl,
    )
    response.raise_for_status()
    return response.text

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
    return f"# Placeholder backup for {device.name} ({device.host})\n# Add a real adapter for vendor={device.vendor}.\n"
