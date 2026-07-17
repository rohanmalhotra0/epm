"""Deployment history persistence (spec section 38)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import Deployment
from ..schemas.api import DeploymentOut
from . import iso


def to_out(d: Deployment) -> DeploymentOut:
    return DeploymentOut(
        id=d.id,
        project_id=d.project_id,
        conversation_id=d.conversation_id,
        environment_name=d.environment_name,
        classification=d.classification,
        application=d.application,
        artifact_name=d.artifact_name,
        artifact_type=d.artifact_type,
        operation=d.operation,
        operation_class=d.operation_class,
        approved=d.approved,
        success=d.success,
        verified=d.verified,
        demo_mode=d.demo_mode,
        checksum=d.checksum,
        context_version=d.context_version,
        rollback_available=d.rollback_available,
        report=d.report or {},
        errors=d.errors or [],
        warnings=d.warnings or [],
        created_at=iso(d.created_at),
    )


def create_deployment(session: Session, project_id: str, **fields) -> Deployment:
    d = Deployment(project_id=project_id, **fields)
    session.add(d)
    session.flush()
    return d


def get_deployment(session: Session, deployment_id: str) -> Deployment | None:
    return session.get(Deployment, deployment_id)


def list_deployments(
    session: Session,
    project_id: str,
    classification: str | None = None,
    artifact_name: str | None = None,
    success: bool | None = None,
) -> list[Deployment]:
    q = session.query(Deployment).filter_by(project_id=project_id)
    if classification:
        q = q.filter_by(classification=classification)
    if artifact_name:
        q = q.filter_by(artifact_name=artifact_name)
    if success is not None:
        q = q.filter_by(success=success)
    return q.order_by(Deployment.created_at.desc()).all()
