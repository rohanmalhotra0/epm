"""Project routes (spec section 10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..schemas.api import ImpactAnalysisOut, ProjectCreate, ProjectOut
from ..services import impact as impact_svc
from ..services import project_bundle
from ..services import projects as svc
from .deps import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _safe_filename(name: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in " _-") else "_" for c in name).strip()
    return cleaned.replace(" ", "_") or "project"


@router.get("", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_db)) -> list[ProjectOut]:
    return svc.list_projects(session)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, session: Session = Depends(get_db)) -> ProjectOut:
    return svc.create_project(session, body.name, body.description)


@router.post("/import", response_model=ProjectOut, status_code=201)
async def import_project(file: UploadFile = File(...), session: Session = Depends(get_db)) -> ProjectOut:
    data = await file.read(project_bundle.MAX_BUNDLE_BYTES + 1)
    if len(data) > project_bundle.MAX_BUNDLE_BYTES:
        raise HTTPException(400, f"bundle exceeds the maximum size of {project_bundle.MAX_BUNDLE_BYTES} bytes")
    try:
        project = project_bundle.import_project(session, data)
    except project_bundle.BundleError as exc:
        raise HTTPException(400, str(exc)) from exc
    return svc._to_out(session, project)


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


@router.get("/{project_id}/export")
def export_project(project_id: str, session: Session = Depends(get_db)) -> Response:
    project = svc.get_project(session, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    zip_bytes = project_bundle.export_project(session, project)
    filename = f"epm-wizard-project-{_safe_filename(project.name)}.zip"
    return Response(content=zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{project_id}/impact", response_model=ImpactAnalysisOut)
def impact_analysis(project_id: str, member: str, session: Session = Depends(get_db)) -> ImpactAnalysisOut:
    if svc.get_project(session, project_id) is None:
        raise HTTPException(404, "project not found")
    try:
        return impact_svc.find_references(session, project_id, member)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: Session = Depends(get_db)) -> None:
    try:
        svc.delete_project(session, project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
