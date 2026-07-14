from __future__ import annotations

from pathlib import Path

import pytest

from netbackup.paths import resolve_inventory_file, resolve_log_file


def test_resolve_inventory_file_allows_project_config(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    inventory = config_dir / "devices.yml"
    inventory.write_text("devices: []\n", encoding="utf-8")

    resolved = resolve_inventory_file(inventory, tmp_path)
    assert resolved == inventory.resolve()


def test_resolve_inventory_file_rejects_outside_project(tmp_path: Path):
    outside = tmp_path.parent / "outside-devices.yml"
    outside.write_text("devices: []\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        resolve_inventory_file(outside, tmp_path)


def test_resolve_log_file_allows_project_log(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "netbackup.log"
    log_file.write_text("INFO ok\n", encoding="utf-8")

    resolved = resolve_log_file(log_file, tmp_path)
    assert resolved == log_file.resolve()


def test_resolve_log_file_rejects_outside_project(tmp_path: Path):
    outside = tmp_path.parent / "outside.log"
    outside.write_text("INFO secret\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        resolve_log_file(outside, tmp_path)
