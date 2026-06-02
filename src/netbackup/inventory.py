from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

@dataclass(frozen=True)
class Device:
    name: str
    host: str
    vendor: str
    method: str
    options: dict[str, Any]

def load_inventory(path: str | Path) -> list[Device]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    devices: list[Device] = []
    for raw in data.get("devices", []):
        required = ["name", "host", "vendor", "method"]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ValueError(f"Device entry missing required fields {missing}: {raw}")
        options = {k: v for k, v in raw.items() if k not in required}
        devices.append(Device(raw["name"], raw["host"], raw["vendor"], raw["method"], options))
    return devices
