"""API dependencies and per-turn context resolution."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..ai.base import AIProvider
from ..ai.registry import resolve_active_provider
from ..config import get_settings
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


def get_current_owner(request: Request) -> str:
    """Resolve the owner identity for the current request.

    Single "local" owner unless multi-user is enabled, in which case the
    identity comes from the reverse-proxy header (default X-Forwarded-Email),
    falling back to "local" when the header is absent.
    """
    settings = get_settings()
    if not settings.multi_user:
        return "local"
    return request.headers.get(settings.auth_email_header) or "local"


def _owner_may_access(project: Project | None, owner: str) -> bool:
    """True when `owner` may touch this project. No-op (always True) unless
    multi-user is on; legacy NULL-owner rows stay visible to everyone."""
    if not get_settings().multi_user:
        return True
    if project is None:
        return True  # a missing project 404s for its own reason, not ownership
    return project.owner_id is None or project.owner_id == owner


def require_project(
    project_id: str,
    session: Session = Depends(get_db),
    owner: str = Depends(get_current_owner),
) -> Project:
    project = projects_svc.get_project(session, project_id)
    if project is None or not _owner_may_access(project, owner):
        raise HTTPException(status_code=404, detail="project not found")
    return project


def authorize_project_id(session: Session, owner: str, project_id: str | None) -> None:
    """Ownership guard for by-ID routes that resolve a resource, then need to
    confirm the caller owns its project. A no-op when multi-user is off, so
    single-user/Demo behavior is unchanged. Raises 404 to avoid leaking
    existence of another owner's resource."""
    if not get_settings().multi_user or project_id is None:
        return
    project = session.get(Project, project_id)
    if not _owner_may_access(project, owner):
        raise HTTPException(status_code=404, detail="not found")


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
    application = env.preferred_application if env else None

    if env is not None and not env.demo and registry.is_connected(env.id):
        connector = registry.get(env.id)  # live connection
        demo = False
        # Prefer the application resolved at connect time.
        application = getattr(connector.info, "application", None) or application
    else:
        # demo connector (always available). Never contacts a tenant. Only the
        # demo path uses the fixture application name.
        from ..connector.demo import DemoConnector
        application = application or "MCWPCF"
        connector = DemoConnector(classification=classification if env else "development", application=application)
        demo = True

    _, provider = resolve_active_provider(session, project.id)
    return TurnContext(
        connector=connector, provider=provider, application=application,
        classification=classification if not demo else (env.classification if env else "development"),
        environment_name=environment_name, demo=demo,
        context_version_id=project.active_context_version_id,
    )
