from __future__ import annotations

from pathlib import Path

from .settings import BACKUP_DIR, BASE_DIR, LOG_FILE


def _is_under_root(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    resolved_root = root.resolve()
    return resolved == resolved_root or resolved_root in resolved.parents


def resolve_backup_file(backup_path: str, backup_root: Path = BACKUP_DIR) -> Path:
    """Resolve a backup file path and ensure it stays under backup_root."""
    path = Path(backup_path).resolve()
    root = backup_root.resolve()
    if not path.is_file() or root not in path.parents:
        raise FileNotFoundError(f"Backup file not found or outside backup root: {backup_path}")
    return path


def resolve_inventory_file(inventory_path: Path, project_root: Path = BASE_DIR) -> Path:
    """Resolve an inventory file and ensure it stays under the project root."""
    path = inventory_path.expanduser().resolve()
    root = project_root.resolve()
    if not path.is_file() or not _is_under_root(path, root):
        raise FileNotFoundError(
            f"Inventory file not found or outside project root: {inventory_path}"
        )
    return path


def resolve_log_file(log_path: Path = LOG_FILE, project_root: Path = BASE_DIR) -> Path:
    """Resolve the application log file and ensure it stays under the project root."""
    path = log_path.expanduser().resolve()
    root = project_root.resolve()
    if not path.is_file() or not _is_under_root(path, root):
        raise FileNotFoundError(f"Log file not found or outside project root: {log_path}")
    return path
