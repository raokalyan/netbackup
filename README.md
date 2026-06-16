# NetBackup

Internal network device configuration backup project.

## Features
- Read device inventory from `config/devices.yml`
- Pull config backups through vendor adapters
- Save timestamped snapshots under `backups/`
- Track backup status in SQLite
- Provide an internal FastAPI web UI/API
- Run from cron or systemd timer on Ubuntu

## Quick start
```bash
cd netbackup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config/devices.example.yml config/devices.yml
PYTHONPATH=src python -m netbackup.backup --inventory config/devices.yml
PYTHONPATH=src uvicorn netbackup.web:app --host 127.0.0.1 --port 8000
# Optional: override the web UI inventory path
# NETBACKUP_INVENTORY=config/devices.yml PYTHONPATH=src uvicorn netbackup.web:app --host 127.0.0.1 --port 8000
```

## Local dummy demo

Use the included dummy inventory to test backups without connecting to a real device:

```bash
cd netbackup
PYTHONPATH=src python3 -m netbackup.backup --inventory config/devices.demo.yml
```

This creates a timestamped config file under `backups/demo-router-01/` with a simple fake network config, including a `hostname` line.

## Panorama / PAN-OS backups

For Panorama, use `vendor: panorama` with `method: api` in `config/devices.yml`. Put your API key in an environment variable or `.env`; do not place the key directly in YAML.

```yaml
devices:
  - name: panorama-01
    host: panorama.example.internal
    vendor: panorama
    method: api
    api_key_env: PANORAMA_API_KEY
    verify_ssl: false
    # Leave commands unset to save a restore-loadable running-config XML file
    # using the PAN-OS export API: type=export&category=configuration.
```

With no `commands` list, the adapter saves a true Panorama/PAN-OS exported configuration file as `.xml`, equivalent to exporting `running-config.xml` for later import/load. You can also explicitly request the same restore file with:

```yaml
commands:
  - export-config
```

If you want a human-readable audit bundle instead of a restore file, add command aliases:

```yaml
commands:
  - system-info
  - panorama-status
  - connected-devices
  - managed-devices
  - device-groups
  - templates
  - template-stacks
  - plugins
```

Supported built-in Panorama command aliases:
- `system-info`
- `panorama-status`
- `connected-devices`
- `managed-devices`
- `device-groups`
- `templates`
- `template-stacks`
- `plugins`
- `full-config`
- `export-config`

You can also add custom PAN-OS API commands:

```yaml
commands:
  - name: commit-jobs
    type: op
    cmd: "<show><jobs><all></all></jobs></show>"
  - name: shared-addresses
    type: config
    action: show
    xpath: "/config/shared/address"
```

If no `commands` list is provided, the adapter defaults to the restore-loadable export API request: `type=export&category=configuration`.

## Security notes
- Do not commit real passwords or API keys.
- Store secrets in `.env` and reference environment variable names in inventory.
- Bind the UI to localhost/VPN or put it behind authenticated Nginx.

## Environment variable naming convention

NetBackup supports per-device secrets with an automatic naming convention, so you can add many devices without env var name collisions.

Convention: `<DEVICE_NAME>_<SECRET_TYPE>` in uppercase, where non-alphanumeric characters in the device name become underscores.

Examples:
- Device `panorama-01` -> `PANORAMA_01_API_KEY`
- Device `firewall-01` -> `FIREWALL_01_API_KEY`
- Device `switch-01` -> `SWITCH_01_USERNAME`, `SWITCH_01_PASSWORD`

The lookup order in the code is:
1. The explicit env var named in the inventory (e.g., `api_key_env: FIREWALL_01_API_KEY`).
2. The auto-generated conventional env var.
3. The global fallback env vars `NETBACKUP_DEFAULT_API_KEY`, `NETBACKUP_DEFAULT_USERNAME`, `NETBACKUP_DEFAULT_PASSWORD`.

This lets you scale to a large fleet by keeping secrets in `.env` and only referencing device names in `config/devices.yml`.

## Web UI
- `/` shows the latest backup runs.
- `/wiki` shows the internal NetBackup wiki and project directory guide.
- `/api/runs` returns recent backup runs as JSON.
