"""API dependencies and per-turn context resolution."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai.base import AIProvider
from ..ai.registry import resolve_active_provider
from ..connector.base import EpmConnector
from ..connector.factory import get_registry
from ..db.base import get_sessionmaker
from ..db.models import Conversation, EnvironmentProfile, Project
from ..services import projects as projects_svc


def get_db() -> Iterator[Session]:
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_project(project_id: str, session: Session = Depends(get_db)) -> Project:
    project = projects_svc.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@dataclass
class TurnContext:
    connector: EpmConnector
    provider: AIProvider
    application: str
    classification: str
    environment_name: str
    demo: bool
    context_version_id: str | None


def resolve_turn(session: Session, project: Project, conversation: Conversation | None = None) -> TurnContext:
    env: EnvironmentProfile | None = None
    if project.active_environment_id:
        env = session.get(EnvironmentProfile, project.active_environment_id)
    if env is None:
        env = session.query(EnvironmentProfile).filter_by(project_id=project.id).first()

    registry = get_registry()
    demo = True
    connector: EpmConnector
    classification = env.classification if env else "development"
    environment_name = env.name if env else "Demo"
    application = (env.preferred_application if env else None) or "MCWPCF"

    if env is not None and not env.demo and registry.is_connected(env.id):
        connector = registry.get(env.id)  # live connection
        demo = False
    else:
        # demo connector (always available). Never contacts a tenant.
        from ..connector.demo import DemoConnector
        connector = DemoConnector(classification=classification if env else "development", application=application)
        demo = True

    _, provider = resolve_active_provider(session, project.id)
    return TurnContext(
        connector=connector, provider=provider, application=application,
        classification=classification if not demo else (env.classification if env else "development"),
        environment_name=environment_name, demo=demo,
        context_version_id=project.active_context_version_id,
    )
