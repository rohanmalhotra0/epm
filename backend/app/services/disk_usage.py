"""Disk usage accounting for the diagnostics page.

Artifact sizes come from the artifact rows themselves: on-disk package files are
measured on disk (the packager writes them under ``<data>/artifacts``); inline
text/JSON artifacts are measured by their stored content size.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import Artifact, Project
from ..schemas.api import DiskUsageOut, ProjectDiskUsageOut
from . import backups


def _db_bytes(session: Session) -> int:
    """Size of the database: the SQLite file, or ``pg_database_size`` on Postgres."""
    settings = get_settings()
    if settings.is_sqlite:
        return settings.db_path.stat().st_size if settings.db_path.exists() else 0
    try:
        return int(session.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0)
    except Exception:
        session.rollback()  # clear the aborted transaction so later queries work
        return 0


def _artifact_bytes(a: Artifact) -> int:
    size = 0
    if a.path:
        p = Path(a.path)
        if p.exists():
            size += p.stat().st_size
    if a.content:
        size += len(a.content.encode("utf-8"))
    if a.payload is not None:
        size += len(json.dumps(a.payload).encode("utf-8"))
    return size


def disk_usage(session: Session) -> DiskUsageOut:
    db_bytes = _db_bytes(session)

    projects: list[ProjectDiskUsageOut] = []
    for project in session.query(Project).order_by(Project.created_at.asc()).all():
        rows = session.query(Artifact).filter_by(project_id=project.id).all()
        projects.append(
            ProjectDiskUsageOut(
                project_id=project.id,
                name=project.name,
                artifact_bytes=sum(_artifact_bytes(a) for a in rows),
                artifact_count=len(rows),
            )
        )

    return DiskUsageOut(
        db_bytes=db_bytes,
        backups_bytes=backups.backups_total_bytes(),
        projects=projects,
    )
