"""Oracle environment profile persistence (spec section 13)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.base import utcnow
from ..db.models import EnvironmentProfile
from ..schemas.api import EnvironmentOut
from . import iso


def to_out(env: EnvironmentProfile, connected: bool = False) -> EnvironmentOut:
    return EnvironmentOut(
        id=env.id,
        project_id=env.project_id,
        name=env.name,
        base_url=env.base_url,
        username=env.username,
        auth_method=env.auth_method,
        classification=env.classification,
        preferred_application=env.preferred_application,
        demo=env.demo,
        connected=connected,
        last_connected_at=iso(env.last_connected_at),
        last_context_refresh_at=iso(env.last_context_refresh_at),
    )


def list_environments(session: Session, project_id: str) -> list[EnvironmentProfile]:
    return (
        session.query(EnvironmentProfile)
        .filter_by(project_id=project_id)
        .order_by(EnvironmentProfile.created_at.asc())
        .all()
    )


def get_environment(session: Session, environment_id: str) -> EnvironmentProfile | None:
    return session.get(EnvironmentProfile, environment_id)


def create_environment(session: Session, project_id: str, **fields) -> EnvironmentProfile:
    env = EnvironmentProfile(project_id=project_id, **fields)
    session.add(env)
    session.flush()
    return env


def delete_environment(session: Session, environment_id: str) -> None:
    env = session.get(EnvironmentProfile, environment_id)
    if env is not None:
        session.delete(env)


def mark_connected(session: Session, environment_id: str) -> None:
    env = session.get(EnvironmentProfile, environment_id)
    if env is not None:
        env.last_connected_at = utcnow()


def mark_context_refreshed(session: Session, environment_id: str) -> None:
    env = session.get(EnvironmentProfile, environment_id)
    if env is not None:
        env.last_context_refresh_at = utcnow()
