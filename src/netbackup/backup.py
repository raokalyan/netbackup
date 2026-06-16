from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
from .adapters import fetch_config
from .inventory import Device, load_inventory
from .settings import BACKUP_DIR
from .storage import record_run

def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)

def backup_extension(device: Device) -> str:
    configured = device.options.get("backup_extension")
    if configured:
        extension = str(configured)
        return extension if extension.startswith(".") else f".{extension}"
    if is_panos_restore_file_backup(device):
        return ".xml"
    return ".cfg"

def is_panos_restore_file_backup(device: Device) -> bool:
    if device.vendor.lower() not in {"panos", "panorama"} or device.method.lower() != "api":
        return False
    commands = device.options.get("commands")
    if not commands:
        return True
    if not isinstance(commands, list) or len(commands) != 1:
        return False
    command = commands[0]
    if command == "export-config":
        return True
    if not isinstance(command, dict):
        return False
    if command.get("alias") == "export-config":
        return True
    return command.get("type") == "export" and command.get("category") == "configuration"

def write_backup(device: Device, content: str, backup_root: Path = BACKUP_DIR) -> Path:
    now = datetime.now()
    target_dir = backup_root / safe_name(device.name) / now.strftime("%Y-%m-%d")
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{now.strftime('%H%M%S')}{backup_extension(device)}"
    path.write_text(content)
    return path

def run_backup(inventory_path: str) -> int:
    failures = 0
    for device in load_inventory(inventory_path):
        try:
            content = fetch_config(device)
            path = write_backup(device, content)
            record_run(device.name, device.host, device.vendor, "success", str(path), "backup completed")
            print(f"OK {device.name}: {path}")
        except Exception as exc:
            failures += 1
            record_run(device.name, device.host, device.vendor, "failed", None, str(exc))
            print(f"FAILED {device.name}: {exc}")
    return 1 if failures else 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Run network device config backups")
    parser.add_argument("--inventory", default="config/devices.yml", help="Path to devices YAML inventory")
    args = parser.parse_args()
    return run_backup(args.inventory)

if __name__ == "__main__":
    raise SystemExit(main())
