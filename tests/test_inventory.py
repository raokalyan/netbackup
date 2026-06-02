from pathlib import Path
from netbackup.inventory import load_inventory


def test_load_inventory(tmp_path: Path):
    inventory = tmp_path / "devices.yml"
    inventory.write_text("""
devices:
  - name: test-fw
    host: 192.0.2.1
    vendor: panos
    method: api
    api_key_env: PANOS_API_KEY
""")
    devices = load_inventory(inventory)
    assert len(devices) == 1
    assert devices[0].name == "test-fw"
    assert devices[0].options["api_key_env"] == "PANOS_API_KEY"
