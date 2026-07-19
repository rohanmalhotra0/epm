"""SQLite database backups with rotation.

Copies the live database into ``<data>/backups`` using the SQLite online backup
API (safe while the app holds open WAL connections). Keeps the newest
``EPMW_BACKUP_KEEP`` files; older backups are deleted. One backup runs at app
startup, more can be created on demand via the diagnostics API.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..config import get_settings
from ..logging import get_logger
from ..schemas.api import BackupFileOut

log = get_logger(__name__)

_BACKUP_PREFIX = "epmwizard-"
_BACKUP_SUFFIX = ".db"


def _backup_files(backups_dir: Path) -> list[Path]:
    """Backup files, newest first (names embed a sortable UTC timestamp)."""
    if not backups_dir.exists():
        return []
    files = [
        p
        for p in backups_dir.iterdir()
        if p.is_file() and p.name.startswith(_BACKUP_PREFIX) and p.name.endswith(_BACKUP_SUFFIX)
    ]
    return sorted(files, key=lambda p: p.name, reverse=True)


def _to_out(path: Path) -> BackupFileOut:
    stat = path.stat()
    return BackupFileOut(
        filename=path.name,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    )


def list_backups() -> list[BackupFileOut]:
    settings = get_settings()
    return [_to_out(p) for p in _backup_files(settings.backups_dir)]


def rotate_backups(keep: int | None = None) -> int:
    """Delete all but the newest ``keep`` backups. Returns how many were removed."""
    settings = get_settings()
    if keep is None:
        keep = settings.backup_keep
    keep = max(keep, 1)
    removed = 0
    for stale in _backup_files(settings.backups_dir)[keep:]:
        try:
            stale.unlink()
            removed += 1
        except OSError as exc:
            log.warning("backup_rotate_failed", file=stale.name, error=str(exc))
    return removed


def create_backup(keep: int | None = None) -> BackupFileOut:
    """Copy the SQLite DB into the backups directory and rotate old backups."""
    settings = get_settings()
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S-%f")
    target = settings.backups_dir / f"{_BACKUP_PREFIX}{stamp}{_BACKUP_SUFFIX}"

    try:
        src = sqlite3.connect(str(settings.db_path))
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise OSError(f"SQLite backup failed: {exc}") from exc

    rotate_backups(keep)
    log.info("backup_created", file=target.name, size=target.stat().st_size)
    return _to_out(target)


def backups_total_bytes() -> int:
    settings = get_settings()
    return sum(p.stat().st_size for p in _backup_files(settings.backups_dir))
