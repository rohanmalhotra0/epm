"""Key/value settings + audit records (spec sections 9, 39)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..db.models import AuditRecord, Setting


def get_setting(session: Session, key: str, project_id: str | None = None, default: Any = None) -> Any:
    scope = "project" if project_id else "global"
    row = session.query(Setting).filter_by(scope=scope, project_id=project_id, key=key).first()
    if row is None:
        return default
    return row.value.get("value", default) if isinstance(row.value, dict) else default


def set_setting(session: Session, key: str, value: Any, project_id: str | None = None) -> None:
    scope = "project" if project_id else "global"
    row = session.query(Setting).filter_by(scope=scope, project_id=project_id, key=key).first()
    if row is None:
        row = Setting(scope=scope, project_id=project_id, key=key, value={"value": value})
        session.add(row)
    else:
        row.value = {"value": value}


def list_settings(session: Session, project_id: str | None = None) -> dict[str, Any]:
    scope = "project" if project_id else "global"
    rows = session.query(Setting).filter_by(scope=scope, project_id=project_id).all()
    return {r.key: (r.value.get("value") if isinstance(r.value, dict) else None) for r in rows}


def record_audit(
    session: Session,
    action: str,
    operation_class: str = "readOnly",
    target: str | None = None,
    environment: str | None = None,
    project_id: str | None = None,
    detail: dict | None = None,
) -> None:
    session.add(
        AuditRecord(
            project_id=project_id,
            action=action,
            operation_class=operation_class,
            target=target,
            environment=environment,
            detail=detail or {},
        )
    )
