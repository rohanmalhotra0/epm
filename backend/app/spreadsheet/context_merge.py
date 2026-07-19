"""Merge an imported hierarchy into the project context — as a NEW version.

ContextVersions are the product's audit story: an existing version is never
mutated. Merging copies the active version's records, appends the imported
members as MemberRecord-shaped ContextRecords and activates the new version
via the same persistence path the context engine uses
(``context_store.persist_context``). With no active context, the new version
contains just the imported records.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import ContextVersion
from ..schemas.context import MemberRecord
from ..services import context_store
from .models import HierarchyParse

_FALLBACK_APPLICATION = "IMPORTED"


def _next_label(session: Session, project_id: str, dimension_name: str) -> str:
    prefix = f"Imported_{dimension_name}_"
    existing = [
        cv for cv in context_store.list_context_versions(session, project_id)
        if cv.label.startswith(prefix)
    ]
    return f"{prefix}{len(existing) + 1}"


def merge_hierarchy_into_context(
    session: Session,
    project_id: str,
    hierarchy: HierarchyParse,
    dimension_name: str,
) -> ContextVersion:
    active = context_store.get_active_context(session, project_id)
    application = active.application if active else _FALLBACK_APPLICATION

    records: list[dict] = []
    if active is not None:
        for r in context_store.get_records(session, active.id):
            records.append({
                "kind": r.kind,
                "name": r.name,
                "dimension": r.dimension,
                "cube": r.cube,
                "alias": r.alias,
                "parent": r.parent,
                "application": r.application,
                "search_text": r.search_text,
                "data": dict(r.data or {}),
            })

    for m in hierarchy.members:
        record = MemberRecord(
            name=m.name,
            dimension=dimension_name,
            application=application,
            alias=m.alias,
            parent=m.parent,
            storage=m.storage,
        )
        records.append({
            "kind": "member",
            "name": m.name,
            "dimension": dimension_name,
            "cube": None,
            "alias": m.alias,
            "parent": m.parent,
            "application": application,
            "search_text": f"{m.name} {m.alias or ''}".strip().lower(),
            "data": record.model_dump(by_alias=True),
        })

    label = _next_label(session, project_id, dimension_name)
    counts = dict(active.counts or {}) if active else {}
    counts["members"] = counts.get("members", 0) + len(hierarchy.members)
    manifest = dict(active.manifest or {}) if active else {}
    manifest.update({
        "mode": "imported",
        "contextVersion": label,
        "counts": counts,
        "importedDimension": dimension_name,
        "importedMemberCount": len(hierarchy.members),
    })

    return context_store.persist_context(
        session,
        project_id,
        application,
        mode="imported",
        label=label,
        manifest=manifest,
        counts=counts,
        records=records,
        fingerprint=active.fingerprint if active else None,
        environment_id=active.environment_id if active else None,
        activate=True,
    )
