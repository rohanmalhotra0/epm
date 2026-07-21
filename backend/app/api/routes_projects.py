"""Project routes (spec section 10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db.models import Project
from ..schemas.api import ImpactAnalysisOut, ProjectCreate, ProjectOut, SearchResponse
from ..services import impact as impact_svc
from ..services import project_bundle
from ..services import projects as svc
from ..services import search as search_svc
from .deps import get_current_owner, get_db, require_project

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _safe_filename(name: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in " _-") else "_" for c in name).strip()
    return cleaned.replace(" ", "_") or "project"


@router.get("", response_model=list[ProjectOut])
def list_projects(
    session: Session = Depends(get_db), owner: str = Depends(get_current_owner)
) -> list[ProjectOut]:
    return svc.list_projects(session, owner=owner)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    session: Session = Depends(get_db),
    owner: str = Depends(get_current_owner),
) -> ProjectOut:
    return svc.create_project(session, body.name, body.description, owner=owner)


@router.post("/import", response_model=ProjectOut, status_code=201)
async def import_project(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    owner: str = Depends(get_current_owner),
) -> ProjectOut:
    data = await file.read(project_bundle.MAX_BUNDLE_BYTES + 1)
    if len(data) > project_bundle.MAX_BUNDLE_BYTES:
        raise HTTPException(400, f"bundle exceeds the maximum size of {project_bundle.MAX_BUNDLE_BYTES} bytes")
    try:
        project = project_bundle.import_project(session, data)
    except project_bundle.BundleError as exc:
        raise HTTPException(400, str(exc)) from exc
    project.owner_id = owner
    session.flush()
    return svc._to_out(session, project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project: Project = Depends(require_project), session: Session = Depends(get_db)) -> ProjectOut:
    return svc._to_out(session, project)


@router.get("/{project_id}/search", response_model=SearchResponse)
def search_project(
    q: str,
    limit: int = 20,
    project: Project = Depends(require_project),
    session: Session = Depends(get_db),
) -> SearchResponse:
    return SearchResponse(results=search_svc.global_search(session, project.id, q, limit))


@router.post("/{project_id}/active-environment/{environment_id}", response_model=ProjectOut)
def set_active_environment(
    environment_id: str,
    project: Project = Depends(require_project),
    session: Session = Depends(get_db),
) -> ProjectOut:
    try:
        svc.set_active_environment(session, project.id, environment_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return svc._to_out(session, project)


@router.post("/{project_id}/active-context/{context_version_id}", response_model=ProjectOut)
def set_active_context(
    context_version_id: str,
    project: Project = Depends(require_project),
    session: Session = Depends(get_db),
) -> ProjectOut:
    from ..services import context_store
    # Confused-deputy guard: the target context must belong to THIS project.
    # Without this, an owner authorized for their own project could point its
    # active context at another owner's context_version_id (resolved purely by
    # id) and exfiltrate that context through their own conversation turns.
    cv = context_store.get_context(session, context_version_id)
    if cv is None or cv.project_id != project.id:
        raise HTTPException(404, "context not found")
    context_store.activate_context(session, project.id, context_version_id)
    return svc._to_out(session, project)


@router.get("/{project_id}/export")
def export_project(
    project: Project = Depends(require_project), session: Session = Depends(get_db)
) -> Response:
    zip_bytes = project_bundle.export_project(session, project)
    filename = f"epm-wizard-project-{_safe_filename(project.name)}.zip"
    return Response(content=zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{project_id}/impact", response_model=ImpactAnalysisOut)
def impact_analysis(
    member: str,
    project: Project = Depends(require_project),
    session: Session = Depends(get_db),
) -> ImpactAnalysisOut:
    try:
        return impact_svc.find_references(session, project.id, member)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project: Project = Depends(require_project), session: Session = Depends(get_db)
) -> None:
    try:
        svc.delete_project(session, project.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
