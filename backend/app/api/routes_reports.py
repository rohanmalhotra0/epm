"""Report + artifact-panel routes.

Powers the Claude-style artifacts panel's *direct* (non-chat) operations:
stateless prompt-editing of a form or report (whole artifact / one table / one
cell), report preview + render, and packaging a report for download. Chat-driven
generation flows through the conversation SSE endpoint + the reports skill; these
endpoints let the panel edit and export an artifact the user already has open.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agent.form_nlu import apply_edit
from ..agent.report_nlu import apply_cell_edit, apply_report_edit, apply_table_edit
from ..artifacts.metadata import build_metadata_from_connector
from ..artifacts.preview import build_preview
from ..artifacts.report_preview import build_report_preview
from ..artifacts.report_renderer import build_report_package, render_report_csv, render_report_html
from ..artifacts.validation import validate_form
from ..config import get_settings
from ..schemas.artifact_edit import ArtifactKind, EditScope, PromptEditRequest, PromptEditResult
from ..schemas.form_preview import FormPreview
from ..schemas.form_spec import FormSpecification
from ..schemas.report_preview import ReportPreview
from ..schemas.report_spec import ReportSpecification
from ..services import artifacts as artifacts_svc
from ..services import projects as projects_svc
from .deps import get_db, resolve_turn

router = APIRouter(prefix="/api", tags=["reports"])


async def _metadata(session: Session, project_id: str | None):
    project = (
        projects_svc.get_project(session, project_id) if project_id
        else projects_svc.get_default_project(session)
    )
    if project is None:
        raise HTTPException(404, "project not found")
    turn = resolve_turn(session, project)
    md = await build_metadata_from_connector(turn.connector, turn.application)
    return project, md


# --- stateless prompt editing (per-artifact / per-table / per-cell) ---------


@router.post("/artifact/edit", response_model=PromptEditResult)
async def artifact_edit(
    body: PromptEditRequest, projectId: str | None = None, session: Session = Depends(get_db)
) -> PromptEditResult:
    _project, md = await _metadata(session, projectId)

    if ArtifactKind(body.artifact_kind) is ArtifactKind.form_spec:
        try:
            spec = FormSpecification.model_validate(body.spec)
        except Exception as exc:
            raise HTTPException(422, f"invalid form spec: {exc}") from exc
        changed, changes, questions = apply_edit(spec, body.instruction, md)
        return PromptEditResult(
            changed=changed, changes=changes, questions=questions,
            spec=spec.model_dump(by_alias=True, exclude_none=True),
            preview=build_preview(spec, md).model_dump(by_alias=True),
            validation=validate_form(spec, md).model_dump(by_alias=True),
        )

    try:
        spec = ReportSpecification.model_validate(body.spec)
    except Exception as exc:
        raise HTTPException(422, f"invalid report spec: {exc}") from exc
    scope = EditScope(body.scope)
    if scope is EditScope.cell:
        changed, changes, questions = apply_cell_edit(
            spec, body.grid_index, body.row_label or "", body.column_label or "", body.instruction, md)
    elif scope is EditScope.table:
        changed, changes, questions = apply_table_edit(spec, body.grid_index, body.instruction, md)
    else:
        changed, changes, questions = apply_report_edit(spec, body.instruction, md)
    return PromptEditResult(
        changed=changed, changes=changes, questions=questions,
        spec=spec.model_dump(by_alias=True, exclude_none=True),
        preview=build_report_preview(spec, md).model_dump(by_alias=True),
    )


# --- previews / render ------------------------------------------------------


@router.post("/forms/preview", response_model=FormPreview)
async def form_preview(spec: dict = Body(..., embed=True), projectId: str | None = None,
                       session: Session = Depends(get_db)) -> FormPreview:
    _project, md = await _metadata(session, projectId)
    return build_preview(FormSpecification.model_validate(spec), md)


@router.post("/reports/preview", response_model=ReportPreview)
async def report_preview(spec: dict = Body(..., embed=True), projectId: str | None = None,
                         session: Session = Depends(get_db)) -> ReportPreview:
    _project, md = await _metadata(session, projectId)
    return build_report_preview(ReportSpecification.model_validate(spec), md)


@router.post("/reports/render")
async def report_render(spec: dict = Body(..., embed=True), projectId: str | None = None,
                        session: Session = Depends(get_db)) -> dict:
    _project, md = await _metadata(session, projectId)
    rspec = ReportSpecification.model_validate(spec)
    preview = build_report_preview(rspec, md)
    return {"html": render_report_html(rspec, preview), "csv": render_report_csv(rspec, preview)}


@router.post("/reports/download")
async def report_download(spec: dict = Body(..., embed=True), projectId: str | None = None,
                          session: Session = Depends(get_db)) -> dict:
    project, md = await _metadata(session, projectId)
    rspec = ReportSpecification.model_validate(spec)
    pkg = build_report_package(rspec, md)
    path = get_settings().artifacts_dir / f"{rspec.name.replace(' ', '_')}_{pkg['checksum'][:12]}.zip"
    path.write_bytes(pkg["zip"])
    artifact = artifacts_svc.save_artifact(
        session, project.id, "reportPackage", f"{rspec.name}.zip",
        path=str(path), checksum=pkg["checksum"], metadata={"manifest": pkg["manifest"]})
    session.flush()
    return {
        "artifactId": artifact.id, "filename": f"{rspec.name}.zip",
        "checksum": pkg["checksum"], "sizeBytes": len(pkg["zip"]),
        "downloadUrl": f"/api/artifacts/{artifact.id}/download",
    }
