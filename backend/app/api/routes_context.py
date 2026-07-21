"""Context routes (spec sections 16-19)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..architecture.service import get_cube_architecture
from ..config import get_settings
from ..context import build_context, import_context_package, search_members
from ..context.engine import environment_fingerprint
from ..context.report_docx import DOCX_MIME, build_context_docx
from ..context.report_pdf import PDF_MIME, build_context_pdf
from ..context.report_md import MD_MIME, build_context_md
from ..schemas.api import ContextVersionOut
from ..db.models import Project
from ..services import context_store, projects
from ..services.attachments import ZIP_MAX_SIZE_BYTES
from .deps import authorize_project_id, get_current_owner, get_db, require_project, resolve_turn

router = APIRouter(tags=["context"])


async def _read_limited(file: UploadFile, limit: int = ZIP_MAX_SIZE_BYTES) -> bytes:
    """Chunked body read with a hard cap — `await file.read()` would buffer an
    arbitrarily large upload into memory before any validation runs."""
    import io
    buffer = io.BytesIO()
    while chunk := await file.read(1024 * 1024):
        buffer.write(chunk)
        if buffer.tell() > limit:
            raise HTTPException(413, f"file exceeds the {limit // (1024 * 1024)} MB limit")
    return buffer.getvalue()


@router.get("/api/projects/{project_id}/contexts", response_model=list[ContextVersionOut])
def list_contexts(project: Project = Depends(require_project),
                  session: Session = Depends(get_db)) -> list[ContextVersionOut]:
    return [context_store.to_out(cv) for cv in context_store.list_context_versions(session, project.id)]


@router.post("/api/projects/{project_id}/contexts/build", response_model=ContextVersionOut)
async def build_project_context(mode: str = "quick", project: Project = Depends(require_project),
                                session: Session = Depends(get_db)) -> ContextVersionOut:
    # `mode` is a caller-supplied query string that ends up as the manifest's
    # ContextMode enum. Reject anything but the two build depths here (422) —
    # otherwise an unknown value would surface as a 500 ValidationError deep in
    # manifest construction. import/snapshot are set by their own routes, never
    # by this endpoint.
    if mode not in ("quick", "deep"):
        raise HTTPException(422, "mode must be 'quick' or 'deep'")
    project_id = project.id
    turn = resolve_turn(session, project)
    fp = environment_fingerprint(None, turn.application, None)
    bundle = await build_context(turn.connector, turn.application, mode=mode, fingerprint=fp)
    cv = context_store.persist_context(session, project_id, bundle.application, bundle.mode, bundle.label,
                                       bundle.manifest.model_dump(by_alias=True), bundle.counts, bundle.records,
                                       fingerprint=bundle.fingerprint)
    # Commit before responding so an immediate follow-up read (e.g. the client
    # refetching the cube architecture, which resolves the now-active context)
    # never races the post-response commit and sees the previous active version.
    session.commit()
    return context_store.to_out(cv)


@router.post("/api/contexts/{context_version_id}/activate", response_model=ContextVersionOut)
def activate(context_version_id: str, session: Session = Depends(get_db),
             owner: str = Depends(get_current_owner)) -> ContextVersionOut:
    cv = context_store.get_context(session, context_version_id)
    if cv is None:
        raise HTTPException(404, "context not found")
    authorize_project_id(session, owner, cv.project_id)
    context_store.activate_context(session, cv.project_id, context_version_id)
    return context_store.to_out(cv)


@router.get("/api/contexts/{context_version_id}/diff")
def diff_context(context_version_id: str, against: str, cap: int = 100,
                 session: Session = Depends(get_db),
                 owner: str = Depends(get_current_owner)) -> dict:
    """Record-level diff between two context versions of the same project
    (spec section 18). Returns per-kind added/removed/changed lists (capped)."""
    cv_a = context_store.get_context(session, context_version_id)
    cv_b = context_store.get_context(session, against)
    if cv_a is None or cv_b is None:
        raise HTTPException(404, "context not found")
    if cv_a.project_id != cv_b.project_id:
        raise HTTPException(400, "contexts belong to different projects")
    authorize_project_id(session, owner, cv_a.project_id)
    return context_store.diff_records(session, cv_a.id, cv_b.id, cap=cap)


@router.delete("/api/contexts/{context_version_id}", status_code=204)
def delete_context(context_version_id: str, session: Session = Depends(get_db),
                   owner: str = Depends(get_current_owner)) -> None:
    cv = context_store.get_context(session, context_version_id)
    if cv is not None:
        authorize_project_id(session, owner, cv.project_id)
    context_store.delete_context(session, context_version_id)


@router.get("/api/projects/{project_id}/architecture")
def project_architecture(cube: str | None = None, project: Project = Depends(require_project),
                         session: Session = Depends(get_db)) -> dict:
    """Cube Architecture for the project's active context, for the Context tab's
    visualizer. Returns the available cubes plus the model for the chosen one."""
    project_id = project.id
    cv = context_store.get_active_context(session, project_id)
    if cv is None:
        raise HTTPException(404, "no active context — build one first")
    md = context_store.build_tenant_metadata(session, cv.id)
    cubes = sorted(md.cubes)
    if not cubes:
        raise HTTPException(404, "the active context has no cubes")
    chosen = cube if cube in md.cubes else cubes[0]
    model = get_cube_architecture(md, chosen, None)
    return {"cubes": cubes, "cube": chosen, "architecture": model.model_dump(by_alias=True)}


def _authorize_context(session: Session, owner: str, context_version_id: str) -> None:
    cv = context_store.get_context(session, context_version_id)
    if cv is not None:
        authorize_project_id(session, owner, cv.project_id)


@router.get("/api/contexts/{context_version_id}/export.docx")
def export_context_word(context_version_id: str, session: Session = Depends(get_db),
                        owner: str = Depends(get_current_owner)) -> Response:
    """A human-readable Word document of the context (opens in Word/Pages/Docs)."""
    _authorize_context(session, owner, context_version_id)
    try:
        filename, data = build_context_docx(session, context_version_id)
    except KeyError as exc:
        raise HTTPException(404, "context not found") from exc
    return Response(content=data, media_type=DOCX_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/api/contexts/{context_version_id}/export.pdf")
def export_context_pdf(context_version_id: str, session: Session = Depends(get_db),
                       owner: str = Depends(get_current_owner)) -> Response:
    """A beautifully formatted PDF report with diagrams and visualizations."""
    _authorize_context(session, owner, context_version_id)
    try:
        filename, data = build_context_pdf(session, context_version_id)
    except KeyError as exc:
        raise HTTPException(404, "context not found") from exc
    return Response(content=data, media_type=PDF_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/api/contexts/{context_version_id}/export.md")
def export_context_markdown(context_version_id: str, session: Session = Depends(get_db),
                            owner: str = Depends(get_current_owner)) -> Response:
    """A Markdown report with Mermaid diagrams (GitHub-compatible)."""
    _authorize_context(session, owner, context_version_id)
    try:
        filename, content = build_context_md(session, context_version_id)
    except KeyError as exc:
        raise HTTPException(404, "context not found") from exc
    return Response(content=content, media_type=MD_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/api/projects/{project_id}/contexts/import", response_model=ContextVersionOut)
async def import_context(file: UploadFile, project: Project = Depends(require_project),
                         session: Session = Depends(get_db)) -> ContextVersionOut:
    project_id = project.id
    data = await _read_limited(file)
    try:
        bundle = import_context_package(data)
    except ValueError as exc:
        raise HTTPException(400, f"invalid context package: {exc}") from exc
    from ..services.attachments import safe_filename
    path = get_settings().contexts_dir / safe_filename(file.filename or f"{bundle.label}.epwcontext")
    path.write_bytes(data)
    cv = context_store.persist_context(session, project_id, bundle.application, bundle.mode, bundle.label,
                                       {"counts": bundle.counts}, bundle.counts, bundle.records,
                                       fingerprint=bundle.fingerprint, path=str(path))
    return context_store.to_out(cv)


@router.post("/api/projects/{project_id}/contexts/snapshot", response_model=ContextVersionOut)
async def import_context_snapshot(file: UploadFile, standalone: bool = False,
                                  project: Project = Depends(require_project),
                                  session: Session = Depends(get_db)) -> ContextVersionOut:
    """Import an LCM application snapshot zip: merged onto the active context
    (default) or as a standalone context version (``?standalone=true``)."""
    # Runtime import: the snapshot parser lives with the context engine.
    from ..context.snapshot import SnapshotError, analyze_snapshot, merge_snapshot_into_context

    project_id = project.id
    data = await _read_limited(file)
    try:
        bundle = analyze_snapshot(data, file.filename)
    except SnapshotError as exc:
        raise HTTPException(400, f"invalid snapshot: {exc}") from exc
    from ..services.attachments import safe_filename
    path = get_settings().contexts_dir / safe_filename(file.filename or "snapshot.zip")
    path.write_bytes(data)
    cv = merge_snapshot_into_context(session, project_id, bundle,
                                     standalone=standalone, filename=file.filename)
    # Commit before responding so the client's immediate architecture/context
    # refetch sees the newly-activated hybrid version, not the previous one.
    session.commit()
    return context_store.to_out(cv)


@router.get("/api/projects/{project_id}/context/search")
def search_context(q: str, dimension: str | None = None, limit: int = 25,
                   project: Project = Depends(require_project),
                   session: Session = Depends(get_db)) -> dict:
    active = context_store.get_active_context(session, project.id)
    if active is None:
        return {"matches": [], "note": "No active context. Build one first."}
    matches = search_members(session, active.id, q, dimension=dimension, limit=limit)
    return {"matches": [m.model_dump(by_alias=True) for m in matches]}
