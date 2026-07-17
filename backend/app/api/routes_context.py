"""Context routes (spec sections 16-19)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..context import build_context, import_context_package, search_members
from ..context.engine import environment_fingerprint
from ..context.package import export_context_package
from ..schemas.api import ContextVersionOut
from ..services import context_store, projects
from .deps import get_db, resolve_turn

router = APIRouter(tags=["context"])


@router.get("/api/projects/{project_id}/contexts", response_model=list[ContextVersionOut])
def list_contexts(project_id: str, session: Session = Depends(get_db)) -> list[ContextVersionOut]:
    return [context_store.to_out(cv) for cv in context_store.list_context_versions(session, project_id)]


@router.post("/api/projects/{project_id}/contexts/build", response_model=ContextVersionOut)
async def build_project_context(project_id: str, mode: str = "quick", session: Session = Depends(get_db)) -> ContextVersionOut:
    project = projects.get_project(session, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    turn = resolve_turn(session, project)
    fp = environment_fingerprint(None, turn.application, None)
    bundle = await build_context(turn.connector, turn.application, mode=mode, fingerprint=fp)
    cv = context_store.persist_context(session, project_id, bundle.application, bundle.mode, bundle.label,
                                       bundle.manifest.model_dump(by_alias=True), bundle.counts, bundle.records,
                                       fingerprint=bundle.fingerprint)
    return context_store.to_out(cv)


@router.post("/api/contexts/{context_version_id}/activate", response_model=ContextVersionOut)
def activate(context_version_id: str, session: Session = Depends(get_db)) -> ContextVersionOut:
    cv = context_store.get_context(session, context_version_id)
    if cv is None:
        raise HTTPException(404, "context not found")
    context_store.activate_context(session, cv.project_id, context_version_id)
    return context_store.to_out(cv)


@router.delete("/api/contexts/{context_version_id}", status_code=204)
def delete_context(context_version_id: str, session: Session = Depends(get_db)) -> None:
    context_store.delete_context(session, context_version_id)


@router.get("/api/contexts/{context_version_id}/export")
def export_context(context_version_id: str, session: Session = Depends(get_db)) -> Response:
    try:
        filename, data = export_context_package(session, context_version_id)
    except KeyError as exc:
        raise HTTPException(404, "context not found") from exc
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/api/projects/{project_id}/contexts/import", response_model=ContextVersionOut)
async def import_context(project_id: str, file: UploadFile, session: Session = Depends(get_db)) -> ContextVersionOut:
    data = await file.read()
    try:
        bundle = import_context_package(data)
    except ValueError as exc:
        raise HTTPException(400, f"invalid context package: {exc}") from exc
    path = get_settings().contexts_dir / (file.filename or f"{bundle.label}.epwcontext")
    path.write_bytes(data)
    cv = context_store.persist_context(session, project_id, bundle.application, bundle.mode, bundle.label,
                                       {"counts": bundle.counts}, bundle.counts, bundle.records,
                                       fingerprint=bundle.fingerprint, path=str(path))
    return context_store.to_out(cv)


@router.get("/api/projects/{project_id}/context/search")
def search_context(project_id: str, q: str, dimension: str | None = None, limit: int = 25,
                   session: Session = Depends(get_db)) -> dict:
    active = context_store.get_active_context(session, project_id)
    if active is None:
        return {"matches": [], "note": "No active context. Build one first."}
    matches = search_members(session, active.id, q, dimension=dimension, limit=limit)
    return {"matches": [m.model_dump(by_alias=True) for m in matches]}
