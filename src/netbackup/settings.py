from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("NETBACKUP_DB", BASE_DIR / "netbackup.db"))
BACKUP_DIR = Path(os.getenv("NETBACKUP_BACKUP_DIR", BASE_DIR / "backups"))
LOG_FILE = Path(os.getenv("NETBACKUP_LOG_FILE", BASE_DIR / "logs" / "netbackup.log"))
