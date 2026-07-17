"""/reports skill — resumable report state machine (agent-generated reports).

Mirrors FormsSkill: build a ReportSpecification from natural language, stream an
Oracle-styled report preview + the spec block (which the artifact panel renders),
apply conversational edits, and package the report for download. Reports are a
read artifact — they are downloaded, not deployed to a tenant.
"""

from __future__ import annotations

import re

from ...artifacts.report_preview import build_report_preview
from ...artifacts.report_renderer import build_report_package
from ...config import get_settings
from ...schemas.report_spec import ReportSpecification
from ...schemas.tools import SkillSpec
from ...services import artifacts as artifacts_svc
from .. import blocks
from ..report_nlu import apply_report_edit, build_initial_report
from .base import Emitter, Skill, SkillContext, SkillResult

_NEW_REPORT = re.compile(r"^(create|build|generate|make)\b.*\breport\b", re.I)
_DOWNLOAD = re.compile(r"\b(download|export|save)\b", re.I)
_CANCEL = re.compile(r"^\s*(cancel|stop|never mind|abort)\s*$", re.I)
_EDIT_ENTRY = re.compile(r"^\s*edit\s*$", re.I)


class ReportsSkill(Skill):
    spec = SkillSpec(
        name="/reports", description="Build, preview, format and download reports.",
        intent_examples=["create a revenue report by month", "show as millions", "add a bar chart", "download the report"],
        required_context=False, approval_required=False,
        allowed_tools=["preview_form", "build_form_package"],
    )

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        text = ctx.user_text
        wf = ctx.workflow
        spec = _load_spec(wf)

        if wf and _CANCEL.match(text):
            await emit.block(blocks.markdown("Cancelled. The report workflow has ended."))
            return SkillResult(skill="reports", workflow_state="cancelled", workflow_active=False)

        if spec is None or _NEW_REPORT.match(text):
            return await self._start(ctx, emit, md, text)
        if _DOWNLOAD.search(text):
            return await self._download(ctx, emit, md, spec)
        if _EDIT_ENTRY.match(text):
            await emit.block(blocks.markdown(
                "Tell me what to change — for example: *show as millions*, *2 decimals*, "
                "*red negatives*, *add a bar chart*, *use descendants instead of children*, "
                "or *highlight values over 500000 red*. You can also open the report in the "
                "artifacts panel (top-right) and edit any cell or table directly."))
            return _persist(spec, "preview")
        return await self._edit(ctx, emit, md, spec, text)

    async def _start(self, ctx: SkillContext, emit: Emitter, md, text: str) -> SkillResult:
        emit.set_steps(blocks.steps("Understanding request", "Resolving members",
                                    "Sampling values", "Formatting", "Rendering report"))
        await emit.step_running(0)
        spec, inferences, _q = build_initial_report(text, md, ctx.application)
        await emit.step_done(0)
        await emit.step_running(1)
        await emit.step_done(1)
        await emit.step_running(2)
        await emit.step_done(2)
        if inferences:
            await emit.prose("Here's what I built from your request and the application:\n\n"
                             + "\n".join(f"- {i}" for i in inferences) + "\n\n")
        await self._emit_preview(ctx, emit, md, spec, steps_from=3)
        return _persist(spec, "preview")

    async def _edit(self, ctx: SkillContext, emit: Emitter, md, spec: ReportSpecification, text: str) -> SkillResult:
        before = _short_json(spec)
        changed, changes, _q = apply_report_edit(spec, text, md)
        if not changed:
            await emit.block(blocks.markdown(
                "I didn't catch a specific change. Try *show as millions*, *2 decimals*, "
                "*add a line chart*, *red negatives*, or *download* when ready."))
            return _persist(spec, "preview")
        await emit.prose("Applied your change:\n\n")
        await emit.block(blocks.diff("Report changes", before, _short_json(spec), language="json"))
        await emit.block(blocks.markdown("\n".join(f"- {c}" for c in changes)))
        await self._emit_preview(ctx, emit, md, spec)
        return _persist(spec, "preview")

    async def _emit_preview(self, ctx: SkillContext, emit: Emitter, md, spec: ReportSpecification, steps_from: int | None = None) -> None:
        if steps_from is not None:
            await emit.step_running(steps_from)
        preview = build_report_preview(spec, md)
        await emit.block(blocks.report_preview(preview))
        await emit.block(blocks.report_specification(spec, preview))
        if steps_from is not None:
            await emit.step_done(steps_from)
        actions = [
            blocks.action("download", "Download report", "download report", "primary"),
            blocks.action("edit", "Edit", "edit"),
            blocks.action("chart", "Add a chart", "add a bar chart"),
            blocks.action("cancel", "Cancel", "cancel", "ghost"),
        ]
        await emit.block(blocks.confirmation(
            "Open it in the artifacts panel (top-right) to edit any cell or table, download it, or keep refining here.",
            actions, severity="info"))

    async def _download(self, ctx: SkillContext, emit: Emitter, md, spec: ReportSpecification) -> SkillResult:
        pkg = build_report_package(spec, md)
        path = get_settings().artifacts_dir / f"{spec.name.replace(' ', '_')}_{pkg['checksum'][:12]}.zip"
        path.write_bytes(pkg["zip"])
        artifact = artifacts_svc.save_artifact(
            ctx.session, ctx.project.id, "reportPackage", f"{spec.name}.zip",
            path=str(path), checksum=pkg["checksum"], metadata={"manifest": pkg["manifest"]},
            source_conversation_id=ctx.conversation.id)
        ctx.session.flush()
        await emit.prose(f"Packaged **{spec.name}** as HTML + CSV + JSON + Markdown "
                         f"(checksum `{pkg['checksum'][:12]}`, {len(pkg['zip']):,} bytes).\n\n")
        await emit.block(blocks.downloadable_file({
            "filename": f"{spec.name}.zip", "artifactId": artifact.id,
            "mediaType": "application/zip", "sizeBytes": len(pkg["zip"]), "checksum": pkg["checksum"],
        }))
        return _persist(spec, "preview")


def _load_spec(wf) -> ReportSpecification | None:
    if wf and wf.data and wf.data.get("spec"):
        try:
            return ReportSpecification.model_validate(wf.data["spec"])
        except Exception:
            return None
    return None


def _persist(spec: ReportSpecification, phase: str) -> SkillResult:
    return SkillResult(
        skill="reports", workflow_state=phase,
        workflow_data={"spec": spec.model_dump(by_alias=True), "phase": phase},
        workflow_active=True,
    )


def _short_json(spec: ReportSpecification) -> str:
    import json
    d = spec.model_dump(by_alias=True, exclude_none=True)
    return json.dumps({k: d[k] for k in ("grids", "display", "businessRuleAssociations", "reportType") if k in d}, indent=2)
