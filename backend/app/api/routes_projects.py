"""Project routes (spec section 10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..schemas.api import ProjectCreate, ProjectOut
from ..services import projects as svc
from .deps import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_db)) -> list[ProjectOut]:
    return svc.list_projects(session)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, session: Session = Depends(get_db)) -> ProjectOut:
    return svc.create_project(session, body.name, body.description)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, session: Session = Depends(get_db)) -> ProjectOut:
    project = svc.get_project(session, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return svc._to_out(session, project)


@router.post("/{project_id}/active-environment/{environment_id}", response_model=ProjectOut)
def set_active_environment(project_id: str, environment_id: str, session: Session = Depends(get_db)) -> ProjectOut:
    try:
        svc.set_active_environment(session, project_id, environment_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return svc._to_out(session, svc.get_project(session, project_id))


@router.post("/{project_id}/active-context/{context_version_id}", response_model=ProjectOut)
def set_active_context(project_id: str, context_version_id: str, session: Session = Depends(get_db)) -> ProjectOut:
    from ..services import context_store
    context_store.activate_context(session, project_id, context_version_id)
    return svc._to_out(session, svc.get_project(session, project_id))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: Session = Depends(get_db)) -> None:
    try:
        svc.delete_project(session, project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
