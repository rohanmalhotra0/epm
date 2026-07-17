"""Artifact storage with versioning (spec sections 27, 37)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import Artifact
from ..schemas.api import ArtifactOut
from . import iso


def to_out(a: Artifact, include_payload: bool = False) -> ArtifactOut:
    return ArtifactOut(
        id=a.id,
        project_id=a.project_id,
        kind=a.kind,
        name=a.name,
        version=a.version,
        checksum=a.checksum,
        context_version=a.context_version,
        has_content=bool(a.content),
        has_file=bool(a.path),
        payload=a.payload if include_payload else None,
        metadata=a.metadata_ or {},
        created_at=iso(a.created_at),
        updated_at=iso(a.updated_at),
    )


def latest_version(session: Session, project_id: str, kind: str, name: str) -> Artifact | None:
    return (
        session.query(Artifact)
        .filter_by(project_id=project_id, kind=kind, name=name)
        .order_by(Artifact.version.desc())
        .first()
    )


def save_artifact(
    session: Session,
    project_id: str,
    kind: str,
    name: str,
    payload: dict | None = None,
    content: str | None = None,
    path: str | None = None,
    checksum: str | None = None,
    context_version: str | None = None,
    source_conversation_id: str | None = None,
    source_message_id: str | None = None,
    metadata: dict | None = None,
) -> Artifact:
    prev = latest_version(session, project_id, kind, name)
    version = (prev.version + 1) if prev else 1
    artifact = Artifact(
        project_id=project_id,
        kind=kind,
        name=name,
        version=version,
        payload=payload,
        content=content,
        path=path,
        checksum=checksum,
        context_version=context_version,
        source_conversation_id=source_conversation_id,
        source_message_id=source_message_id,
        parent_artifact_id=prev.id if prev else None,
        metadata_=metadata or {},
    )
    session.add(artifact)
    session.flush()
    return artifact


def get_artifact(session: Session, artifact_id: str) -> Artifact | None:
    return session.get(Artifact, artifact_id)


def list_artifacts(session: Session, project_id: str, kind: str | None = None) -> list[Artifact]:
    q = session.query(Artifact).filter_by(project_id=project_id)
    if kind:
        q = q.filter_by(kind=kind)
    return q.order_by(Artifact.updated_at.desc()).all()


def delete_artifact(session: Session, artifact_id: str) -> None:
    artifact = session.get(Artifact, artifact_id)
    if artifact is not None:
        session.delete(artifact)
