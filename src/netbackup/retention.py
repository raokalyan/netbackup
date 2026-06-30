from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .logging_setup import setup_logging
from .settings import BACKUP_DIR, RETENTION_DAYS
from .storage import purge_runs_older_than

logger = setup_logging()


def apply_retention(
    backup_root: Path = BACKUP_DIR,
    retention_days: int = RETENTION_DAYS,
) -> tuple[int, int]:
    """Delete backup files and DB rows older than retention_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    files_deleted = _purge_backup_files(backup_root, cutoff)
    rows_deleted = purge_runs_older_than(cutoff)
    if files_deleted or rows_deleted:
        logger.info(
            "Retention (%s days): removed %s file(s) and %s database row(s)",
            retention_days,
            files_deleted,
            rows_deleted,
        )
    return files_deleted, rows_deleted


def _purge_backup_files(backup_root: Path, cutoff: datetime) -> int:
    if not backup_root.exists():
        return 0

    deleted = 0
    for path in backup_root.rglob("*"):
        if not path.is_file():
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            path.unlink(missing_ok=True)
            deleted += 1

    _remove_empty_dirs(backup_root)
    return deleted


def _remove_empty_dirs(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                continue
