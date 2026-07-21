"""Context version + record persistence and metadata reconstruction (spec 16-19)."""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..artifacts.metadata import TenantMetadata, build_metadata
from ..db.models import ContextRecord, ContextVersion, Project
from ..schemas.api import ContextVersionOut
from ..schemas.context import (
    CubeRecord,
    DimensionRecord,
    FormRecord,
    MemberRecord,
    RuleRecord,
    VariableRecord,
)
from . import iso


def to_out(cv: ContextVersion) -> ContextVersionOut:
    return ContextVersionOut(
        id=cv.id,
        project_id=cv.project_id,
        application=cv.application,
        label=cv.label,
        mode=cv.mode,
        counts=cv.counts or {},
        active=cv.active,
        manifest=cv.manifest or {},
        created_at=iso(cv.created_at),
    )


def persist_context(
    session: Session,
    project_id: str,
    application: str,
    mode: str,
    label: str,
    manifest: dict,
    counts: dict,
    records: list[dict],
    fingerprint: str | None = None,
    environment_id: str | None = None,
    path: str | None = None,
    activate: bool = True,
) -> ContextVersion:
    cv = ContextVersion(
        project_id=project_id,
        environment_id=environment_id,
        application=application,
        label=label,
        mode=mode,
        manifest=manifest,
        counts=counts,
        fingerprint=fingerprint,
        path=path,
        active=False,
    )
    session.add(cv)
    session.flush()
    for rec in records:
        session.add(ContextRecord(context_version_id=cv.id, project_id=project_id, **rec))
    if activate:
        activate_context(session, project_id, cv.id)
    return cv


def activate_context(session: Session, project_id: str, context_version_id: str) -> None:
    session.query(ContextVersion).filter_by(project_id=project_id, active=True).update({"active": False})
    cv = session.get(ContextVersion, context_version_id)
    if cv is not None:
        cv.active = True
    project = session.get(Project, project_id)
    if project is not None:
        project.active_context_version_id = context_version_id


def list_context_versions(session: Session, project_id: str) -> list[ContextVersion]:
    return (
        session.query(ContextVersion)
        .filter_by(project_id=project_id)
        .order_by(ContextVersion.created_at.desc())
        .all()
    )


def get_active_context(session: Session, project_id: str) -> ContextVersion | None:
    return session.query(ContextVersion).filter_by(project_id=project_id, active=True).first()


def get_context(session: Session, context_version_id: str) -> ContextVersion | None:
    return session.get(ContextVersion, context_version_id)


def get_records(session: Session, context_version_id: str, kind: str | None = None) -> list[ContextRecord]:
    q = session.query(ContextRecord).filter_by(context_version_id=context_version_id)
    if kind:
        q = q.filter_by(kind=kind)
    return q.all()


def _validate_known(model_cls, data: dict):
    # Snapshot-derived records carry provenance keys ("source", "referencedOnly",
    # rule bodies…) that the strict record models forbid; keep only known fields.
    # ``data`` may be None or a non-mapping on hostile/partial records — coerce to
    # an empty dict so filtering never raises (validation then rejects it cleanly).
    if not isinstance(data, dict):
        data = {}
    fields = model_cls.model_fields
    allowed = set(fields) | {f.alias for f in fields.values() if f.alias}
    return model_cls.model_validate({k: v for k, v in data.items() if k in allowed})


def build_tenant_metadata(session: Session, context_version_id: str) -> TenantMetadata:
    """Reconstruct TenantMetadata from persisted records (for the artifact engine)."""
    cv = session.get(ContextVersion, context_version_id)
    application = cv.application if cv else ""
    records = get_records(session, context_version_id)
    kinds = {"cube": (CubeRecord, []), "dimension": (DimensionRecord, []),
             "member": (MemberRecord, []), "variable": (VariableRecord, []),
             "form": (FormRecord, []), "rule": (RuleRecord, [])}
    for r in records:
        entry = kinds.get(r.kind)
        if entry is None:
            continue
        try:
            entry[1].append(_validate_known(entry[0], r.data))
        except (ValidationError, ValueError, TypeError):
            # A record whose persisted `data` can't satisfy its strict model
            # (missing required field, wrong type, non-mapping) is skipped —
            # one bad record must never sink the whole metadata reconstruction.
            continue
    return build_metadata(application, kinds["cube"][1], kinds["dimension"][1], kinds["member"][1],
                          kinds["variable"][1], kinds["form"][1], kinds["rule"][1])


def _record_to_dict(r: ContextRecord) -> dict:
    return {
        "kind": r.kind,
        "name": r.name,
        "dimension": r.dimension,
        "cube": r.cube,
        "alias": r.alias,
        "parent": r.parent,
        "application": r.application,
        "data": r.data or {},
    }


def diff_records(session: Session, version_a_id: str, version_b_id: str, cap: int = 100) -> dict:
    """Record-level diff between two persisted context versions (spec section 18).

    Delegates to ``engine.diff_context_records`` and wraps the per-kind result
    with both versions' ids/labels for the Context tab's detailed diff view.
    """
    from ..context.engine import diff_context_records  # runtime import: avoid cycle

    cv_a = session.get(ContextVersion, version_a_id)
    cv_b = session.get(ContextVersion, version_b_id)
    recs_a = [_record_to_dict(r) for r in get_records(session, version_a_id)]
    recs_b = [_record_to_dict(r) for r in get_records(session, version_b_id)]
    return {
        "versionA": {"id": cv_a.id if cv_a else version_a_id, "label": cv_a.label if cv_a else None},
        "versionB": {"id": cv_b.id if cv_b else version_b_id, "label": cv_b.label if cv_b else None},
        "kinds": diff_context_records(recs_a, recs_b, cap=cap),
    }


def delete_context(session: Session, context_version_id: str) -> None:
    cv = session.get(ContextVersion, context_version_id)
    if cv is not None:
        session.delete(cv)
        from ..rag import invalidate_rag_index  # runtime import: rag depends on this module
        invalidate_rag_index(context_version_id)
