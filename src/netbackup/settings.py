from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("NETBACKUP_DB", BASE_DIR / "netbackup.db"))
BACKUP_DIR = Path(os.getenv("NETBACKUP_BACKUP_DIR", BASE_DIR / "backups"))
LOG_FILE = Path(os.getenv("NETBACKUP_LOG_FILE", BASE_DIR / "logs" / "netbackup.log"))

# Fallback credentials used when a device-specific env var is not set.
DEFAULT_API_KEY = os.getenv("NETBACKUP_DEFAULT_API_KEY")
DEFAULT_USERNAME = os.getenv("NETBACKUP_DEFAULT_USERNAME")
DEFAULT_PASSWORD = os.getenv("NETBACKUP_DEFAULT_PASSWORD")


def device_env_name(device_name: str, secret_type: str) -> str:
    """Return the conventional env var name for a device secret.

    The convention is ``<DEVICE_NAME>_<SECRET_TYPE>`` in uppercase, with
    any non-alphanumeric character in the device name converted to an underscore.

    Examples:
        >>> device_env_name("panorama-01", "api_key")
        'PANORAMA_01_API_KEY'
        >>> device_env_name("switch-01", "username")
        'SWITCH_01_USERNAME'
    """
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in device_name).upper()
    return f"{sanitized}_{secret_type.upper()}"


def resolve_device_secret(
    device_name: str,
    secret_type: str,
    explicit_env: str | None = None,
) -> str | None:
    """Resolve a device secret from the environment.

    Lookup order:
    1. ``explicit_env`` if the device inventory names a specific env var.
    2. The auto-generated conventional env var for this device and secret type.
    3. The global fallback env var for the secret type.
    """
    if explicit_env:
        value = os.getenv(explicit_env)
        if value:
            return value

    value = os.getenv(device_env_name(device_name, secret_type))
    if value:
        return value

    fallback_map = {
        "API_KEY": "NETBACKUP_DEFAULT_API_KEY",
        "USERNAME": "NETBACKUP_DEFAULT_USERNAME",
        "PASSWORD": "NETBACKUP_DEFAULT_PASSWORD",
    }
    fallback_env = fallback_map.get(secret_type.upper())
    return os.getenv(fallback_env) if fallback_env else None
