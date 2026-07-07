# NetBackup Internal Wiki

NetBackup is an internal network device configuration backup system. It reads device inventory, connects through vendor adapters, saves timestamped config snapshots, records backup status in SQLite, and exposes recent results through the web UI.

## Directory and File Guide

```text
netbackup/
├── README.md                 # Main quick-start documentation
├── requirements.txt          # Python dependencies for pip install
├── pyproject.toml            # Python package metadata and pytest config
├── .env.example              # Template for runtime settings and secrets
├── .gitignore                # Keeps local secrets/generated files out of Git
├── config/                   # Device inventory files
├── backups/                  # Saved device configuration snapshots
├── logs/                     # Runtime logs
├── docs/                     # Web-visible documentation/wiki pages
├── scripts/                  # Cron/manual helper scripts
├── systemd/                  # Ubuntu systemd service and timer examples
├── src/                      # Python application source code
└── tests/                    # Automated tests
```

## Top-Level Files

### README.md
Main project documentation. Use it for first-time setup, quick-start commands, and high-level security notes.

### requirements.txt
Python packages required to run the app. Install with `pip install -r requirements.txt`.

### pyproject.toml
Project metadata and tool configuration. It identifies the project as `netbackup`, sets the Python version requirement, and configures pytest to use `src/`.

### .env.example
Template for environment variables. Copy it to `.env` on the server and place real runtime values there. Do not commit real passwords or API keys.

### .gitignore
Prevents local secrets, virtual environments, databases, logs, and generated files from being committed.

## Directories

### config/
Stores device inventory files.

- `devices.example.yml`: safe example inventory file.
- `devices.yml`: expected production inventory file with real devices, IPs, vendors, and credential environment-variable references.

### backups/
Stores generated network configuration snapshots. The `.gitkeep` file only preserves the empty directory in Git.

### logs/
Stores runtime logs, normally including `netbackup.log`. Use this when troubleshooting failed backups, authentication issues, or adapter errors.

### docs/
Stores documentation intended for users and maintainers. This wiki file lives at `docs/wiki.md` and is available from the web UI at `/wiki`.

### scripts/
Operational helper scripts.

- `run_backup.sh`: runs the backup process (loads `.env`, uses `--skip-if-busy` for cron).
- `cron.example`: sample cron schedule. The active example runs every 5 minutes for testing.

### systemd/
Ubuntu systemd automation examples.

- `netbackup-backup.service`: one backup execution.
- `netbackup-backup.timer`: nightly production schedule.
- `netbackup-backup-testing.timer`: every 5 minutes for testing.

Systemd timers are often preferred over cron because they provide better status and logging through `systemctl` and `journalctl`.

### src/netbackup/
Python application code.

- `__init__.py`: marks the package.
- `settings.py`: loads environment settings and important paths.
- `inventory.py`: reads and validates YAML device inventory.
- `adapters.py`: vendor connection logic. This is where Palo Alto, Cisco, Fortinet, Juniper, or other device adapters belong.
- `backup.py`: command-line backup runner.
- `storage.py`: SQLite backup-run database functions.
- `web.py`: FastAPI web UI and API routes.

### tests/
Automated tests for project behavior. Current tests focus on inventory loading. Add tests here when adding new device adapters or web/API features.

## How the Backup Flow Works

1. A scheduled job runs `scripts/run_backup.sh` or `python -m netbackup.backup`.
2. `backup.py` loads devices from `config/devices.yml`.
3. Each device is sent to the correct adapter in `adapters.py`.
4. The adapter retrieves configuration text from the device.
5. The backup is saved under `backups/`.
6. The result is recorded in SQLite through `storage.py`.
7. The web UI reads recent runs and displays status.

## Web UI Pages

- `/`: latest backup runs table.
- `/wiki`: this internal wiki page.
- `/api/runs`: JSON API for recent backup runs.

## Operating Notes

- Keep the web UI internal only, preferably bound to localhost, VPN, or protected by authenticated Nginx.
- Keep secrets in `.env` and reference them from inventory instead of storing secrets directly in YAML.
- Review `logs/` after failed runs.
- Check `backups/` to confirm snapshots are being created.
- Add vendor-specific logic in `src/netbackup/adapters.py` as new device types are introduced.

## Common Commands

```bash
# Run a manual backup
PYTHONPATH=src python3 -m netbackup.backup --inventory config/devices.yml

# Start the internal web UI
PYTHONPATH=src uvicorn netbackup.web:app --host 127.0.0.1 --port 8000

# Run tests
PYTHONPATH=src python3 -m pytest
```

## Security Rules

- Never commit real passwords, API keys, or firewall credentials.
- Restrict access to the web UI.
- Use least-privilege backup accounts where supported.
- Protect the Ubuntu server and filesystem backups.
- Consider encrypting long-term archives.

## Local Dummy Device Demo

A local dummy inventory is included for testing before connecting to real network devices:

- Inventory file: `config/devices.demo.yml`
- Device name: `demo-router-01`
- Host: `127.0.0.1`
- Vendor/method: `dummy` / `dummy`

Run it with:

```bash
cd netbackup
PYTHONPATH=src python3 -m netbackup.backup --inventory config/devices.demo.yml
```

The dummy adapter does not make any network connection. It generates a small fake config backup with lines like:

```text
hostname demo-router-01
interface loopback0
 description Local demo interface
```

The backup will be written under:

```text
backups/demo-router-01/YYYY-MM-DD/HHMMSS.cfg
```

This is the safest way to test the backup runner, backup storage path, SQLite run history, and web UI status page before adding real device credentials.
