"""Project CRUD and active target selection (spec section 10)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import Conversation, EnvironmentProfile, Project
from ..schemas.api import ProjectOut
from . import iso


def _to_out(session: Session, p: Project) -> ProjectOut:
    count = session.query(func.count(Conversation.id)).filter_by(project_id=p.id).scalar() or 0
    return ProjectOut(
        id=p.id,
        name=p.name,
        description=p.description,
        is_default=p.is_default,
        active_environment_id=p.active_environment_id,
        active_context_version_id=p.active_context_version_id,
        settings=p.settings or {},
        conversation_count=count,
        created_at=iso(p.created_at),
        updated_at=iso(p.updated_at),
    )


def _owner_visible(owner: str):
    """Rows owned by ``owner`` plus legacy NULL-owner rows (visible to all).

    When multi-user is off every row carries the "local" owner (or NULL), so
    this predicate is a no-op filter and behavior is unchanged.
    """
    return (Project.owner_id == owner) | (Project.owner_id.is_(None))


def list_projects(session: Session, owner: str = "local") -> list[ProjectOut]:
    projects = (
        session.query(Project)
        .filter(_owner_visible(owner))
        .order_by(Project.created_at.asc())
        .all()
    )
    if not projects and owner != "local":
        # Multi-user: first request from a new user. The seeded default project
        # belongs to "local", so a fresh Google-authenticated user sees nothing
        # and the UI has no project to create chats in. Provision theirs here.
        project = Project(
            name="My Project",
            description="Your workspace. Sign in to an Oracle EPM environment to begin.",
            is_default=False,
            owner_id=owner,
        )
        session.add(project)
        session.flush()
        projects = [project]
    return [_to_out(session, p) for p in projects]


def get_project(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def get_default_project(session: Session, owner: str = "local") -> Project | None:
    base = session.query(Project).filter(_owner_visible(owner))
    return base.filter(Project.is_default.is_(True)).first() or base.first()


def create_project(
    session: Session, name: str, description: str | None = None, owner: str = "local"
) -> ProjectOut:
    project = Project(name=name, description=description, is_default=False, owner_id=owner)
    session.add(project)
    session.flush()
    return _to_out(session, project)


def update_project(
    session: Session, project_id: str, name: str | None = None, description: str | None = None
) -> ProjectOut | None:
    """Rename / re-describe a project. Only non-None fields are applied; a blank
    name is rejected so the UI can't strand a project with an empty label."""
    project = session.get(Project, project_id)
    if project is None:
        return None
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        project.name = cleaned
    if description is not None:
        project.description = description
    session.flush()
    return _to_out(session, project)


def set_active_environment(session: Session, project_id: str, environment_id: str | None) -> None:
    project = session.get(Project, project_id)
    if project is None:
        raise KeyError("project not found")
    if environment_id is not None:
        env = session.get(EnvironmentProfile, environment_id)
        if env is None or env.project_id != project_id:
            raise ValueError("environment does not belong to project")
    project.active_environment_id = environment_id


def set_active_context(session: Session, project_id: str, context_version_id: str | None) -> None:
    project = session.get(Project, project_id)
    if project is None:
        raise KeyError("project not found")
    project.active_context_version_id = context_version_id


def delete_project(session: Session, project_id: str) -> None:
    project = session.get(Project, project_id)
    if project is None:
        return
    if project.is_default:
        raise ValueError("cannot delete the default project")
    session.delete(project)
