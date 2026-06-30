from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from .backup import _backup_lock, _execute_backup
from .logging_setup import setup_logging

logger = setup_logging()

JobStatus = Literal["idle", "running", "completed", "failed", "busy"]


@dataclass
class BackupJobState:
    status: JobStatus = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    message: str | None = None
    inventory_path: str | None = None


_state = BackupJobState()
_state_lock = threading.Lock()


def get_job_state() -> BackupJobState:
    with _state_lock:
        return BackupJobState(
            status=_state.status,
            started_at=_state.started_at,
            finished_at=_state.finished_at,
            exit_code=_state.exit_code,
            message=_state.message,
            inventory_path=_state.inventory_path,
        )


def start_backup_job(inventory_path: str) -> BackupJobState:
    """Start a backup in a background thread. Returns current job state."""
    if not _backup_lock.acquire(blocking=False):
        with _state_lock:
            _state.status = "busy"
            _state.message = "A backup is already running"
        logger.warning("Backup request rejected: another backup is in progress")
        return get_job_state()

    started = datetime.now(timezone.utc).isoformat()
    with _state_lock:
        _state.status = "running"
        _state.started_at = started
        _state.finished_at = None
        _state.exit_code = None
        _state.message = "Backup in progress"
        _state.inventory_path = inventory_path

    def _run() -> None:
        logger.info("Background backup started for inventory %s", inventory_path)
        try:
            exit_code = _execute_backup(inventory_path)
        except Exception as exc:
            with _state_lock:
                _state.status = "failed"
                _state.finished_at = datetime.now(timezone.utc).isoformat()
                _state.exit_code = 1
                _state.message = str(exc)
            logger.exception("Background backup crashed")
            return
        finally:
            _backup_lock.release()

        finished = datetime.now(timezone.utc).isoformat()
        with _state_lock:
            _state.status = "completed" if exit_code == 0 else "failed"
            _state.finished_at = finished
            _state.exit_code = exit_code
            _state.message = (
                "Backup completed successfully"
                if exit_code == 0
                else "Backup finished with errors"
            )
        logger.info("Background backup finished with exit code %s", exit_code)

    thread = threading.Thread(target=_run, name="netbackup-job", daemon=True)
    thread.start()
    return get_job_state()
