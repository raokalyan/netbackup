from __future__ import annotations

from pathlib import Path

from .settings import BACKUP_DIR


def resolve_backup_file(backup_path: str, backup_root: Path = BACKUP_DIR) -> Path:
    """Resolve a backup file path and ensure it stays under backup_root."""
    path = Path(backup_path).resolve()
    root = backup_root.resolve()
    if not path.is_file() or root not in path.parents:
        raise FileNotFoundError(f"Backup file not found or outside backup root: {backup_path}")
    return path
