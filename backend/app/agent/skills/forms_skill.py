"""/forms skill — resumable form state machine (spec sections 20-29)."""

from __future__ import annotations

import re

from ...architecture import service as arch
from ...artifacts.packager import build_form_package
from ...artifacts.preview import build_preview
from ...artifacts.validation import validate_form
from ...config import get_settings
from ...schemas.deployment import FormWorkflowState
from ...schemas.form_spec import FormSpecification
from ...schemas.tools import SkillSpec
from ...services import artifacts as artifacts_svc
from .. import blocks
from ..deploy import build_deployment_plan, execute_deployment
from ..form_nlu import apply_edit, build_initial_spec
from .base import Emitter, Skill, SkillContext, SkillResult

_NEW_FORM = re.compile(r"^(create|build|generate)\b.*\bform\b", re.I)
_DEPLOY = re.compile(r"\b(deploy|confirm deploy|create the form|create it|yes,? deploy)\b", re.I)
_DOWNLOAD = re.compile(r"\bdownload\b", re.I)
_CANCEL = re.compile(r"^\s*(cancel|stop|never mind|abort)\s*$", re.I)
_COVERAGE = re.compile(r"\b(coverage|architecture|dimensionality|how (this|my) form|missing dimension)\b", re.I)
_EDIT_ENTRY = re.compile(r"^\s*edit\s*$", re.I)


class FormsSkill(Skill):
    spec = SkillSpec(
        name="/forms", description="Build, preview, edit and deploy data forms.",
        intent_examples=["create an Actuals form", "hide March", "move Entity to POV", "deploy the form"],
        required_context=False, approval_required=True,
        allowed_tools=["validate_form_spec", "preview_form", "build_form_package", "import_snapshot", "verify_form"],
    )

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        text = ctx.user_text
        wf = ctx.workflow
        spec = _load_spec(wf)
        phase = (wf.data.get("phase") if wf and wf.data else None) or None

        if wf and _CANCEL.match(text):
            await emit.block(blocks.markdown("Cancelled. The form workflow has ended."))
            return SkillResult(skill="forms", workflow_state=FormWorkflowState.cancelled.value, workflow_active=False)

        if spec is None or _NEW_FORM.match(text):
            return await self._start(ctx, emit, md, text)

        if _DOWNLOAD.search(text):
            return await self._download(ctx, emit, spec)
        if _COVERAGE.search(text):
            return await self._coverage(ctx, emit, md, spec, phase)
        if _EDIT_ENTRY.match(text):
            await emit.block(blocks.markdown(
                "Sure — tell me what to change. For example: *hide March*, *move Entity to POV*, "
                "*use level-zero descendants of Total Payroll*, or *attach the IR rule*."))
            return _persist(spec, "preview")
        if _DEPLOY.search(text):
            return await self._deploy(ctx, emit, md, spec, phase, text)

        # otherwise: a conversational edit
        return await self._edit(ctx, emit, md, spec, text)

    # --- phases -------------------------------------------------------------

    async def _start(self, ctx: SkillContext, emit: Emitter, md, text: str) -> SkillResult:
        emit.set_steps(blocks.steps("Understanding request", "Searching EPM context", "Retrieving grounding",
                                    "Resolving members", "Validating form", "Generating preview"))
        await emit.step_running(0)
        spec, inferences, questions = build_initial_spec(text, md, ctx.application)
        await emit.step_done(0)
        await emit.step_running(1)
        await emit.step_done(1)
        await emit.step_running(2)
        grounding = await _retrieve_grounding(ctx, kinds=["form", "rule", "member", "variable"], k=5)
        await emit.step_done(2)
        await emit.step_running(3)
        await emit.step_done(3)

        if inferences:
            await emit.prose("Here's what I inferred from your request and the existing application:\n\n"
                             + "\n".join(f"- {i}" for i in inferences) + "\n\n")
        await self._emit_questions(emit, questions)
        if (grounding_block := _grounding_block(ctx.user_text, "form", grounding)) is not None:
            await emit.block(grounding_block)
        await self._emit_preview(ctx, emit, md, spec, steps_from=4)
        return _persist(spec, "preview", FormWorkflowState.preview_ready)

    async def _edit(self, ctx: SkillContext, emit: Emitter, md, spec: FormSpecification, text: str) -> SkillResult:
        before = spec.model_copy(deep=True)
        changed, changes, questions = apply_edit(spec, text, md)
        if not changed:
            await emit.block(blocks.markdown(
                "I didn't catch a specific change. Try things like *hide March*, *move Entity to POV*, "
                "*use descendants instead of children*, *only show five members*, or say *deploy* when ready."))
            return _persist(spec, "preview")
        await emit.prose("Applied your change:\n\n")
        await emit.block(blocks.diff("Form changes",
                                     _short_json(before), _short_json(spec), language="json"))
        await emit.block(blocks.markdown("\n".join(f"- {c}" for c in changes)))
        await self._emit_questions(emit, questions)
        await self._emit_preview(ctx, emit, md, spec)
        return _persist(spec, "preview", FormWorkflowState.awaiting_user_changes)

    async def _emit_questions(self, emit: Emitter, questions: list[str]) -> None:
        """Surface the builder's open questions — a default it had to guess at is
        only useful to the user if they're told it was a guess."""
        if questions:
            await emit.block(blocks.markdown(
                "A couple of things I need you to confirm:\n\n"
                + "\n".join(f"- {q}" for q in questions)))

    async def _emit_preview(self, ctx: SkillContext, emit: Emitter, md, spec: FormSpecification, steps_from: int | None = None) -> None:
        report = validate_form(spec, md)
        if steps_from is not None:
            await emit.step_running(steps_from)
        preview = build_preview(spec, md)
        await emit.block(blocks.form_preview(preview))
        await emit.block(blocks.form_specification(spec))
        await emit.block(blocks.validation_report(report))
        if steps_from is not None:
            await emit.step_done(steps_from)
        actions = [
            blocks.action("deploy", f"Deploy to {ctx.environment_name}", "deploy", "primary"),
            blocks.action("edit", "Edit", "edit"),
            blocks.action("coverage", "Show form coverage", "show form coverage"),
            blocks.action("download", "Download only", "download only"),
            blocks.action("cancel", "Cancel", "cancel", "ghost"),
        ]
        prompt = ("Ready to create this form?" if report.valid
                  else "This form has validation errors — fix them before deploying.")
        await emit.block(blocks.confirmation(prompt, actions, severity="info" if report.valid else "warning"))

    async def _coverage(self, ctx: SkillContext, emit: Emitter, md, spec: FormSpecification, phase) -> SkillResult:
        model = arch.get_cube_architecture(md, spec.cube, spec)
        report = arch.validate_dimension_coverage(md, spec.cube, spec)
        size = arch.cross_dimensional_size(md, spec.cube, spec)
        await emit.prose(f"Here's how **{spec.name}** uses cube **{spec.cube}**:\n\n")
        await emit.block(blocks._block(_ct("cubeArchitecture"), model.model_dump(by_alias=True)))
        await emit.block(blocks._block(_ct("dimensionCoverage"), report.model_dump(by_alias=True)))
        cov_note = (f"**{len(report.covered_dimensions)} of {model.dimension_count}** cube dimensions are placed on the form. "
                    + (f"Missing: {', '.join(report.missing_dimensions)} (will default)." if report.missing_dimensions else "All dimensions handled."))
        await emit.block(blocks.markdown(cov_note + f"\n\nPotential intersections: **{size.total_potential_cells:,}** cells."))
        return _persist(spec, phase or "preview")

    async def _download(self, ctx: SkillContext, emit: Emitter, spec: FormSpecification) -> SkillResult:
        pkg = build_form_package(spec)
        path = get_settings().artifacts_dir / f"{spec.name.replace(' ', '_')}_{pkg['checksum'][:12]}.zip"
        path.write_bytes(pkg["zip"])
        artifact = artifacts_svc.save_artifact(ctx.session, ctx.project.id, "package", f"{spec.name}.zip",
                                               path=str(path), checksum=pkg["checksum"],
                                               metadata={"manifest": pkg["manifest"]},
                                               source_conversation_id=ctx.conversation.id)
        ctx.session.flush()
        await emit.prose(f"Built a deterministic package for **{spec.name}** "
                         f"(checksum `{pkg['checksum'][:12]}`, {len(pkg['zip']):,} bytes).\n\n")
        await emit.block(blocks.downloadable_file({
            "filename": f"{spec.name}.zip", "artifactId": artifact.id,
            "mediaType": "application/zip", "sizeBytes": len(pkg["zip"]), "checksum": pkg["checksum"],
        }))
        return _persist(spec, "preview")

    async def _deploy(self, ctx: SkillContext, emit: Emitter, md, spec: FormSpecification, phase, text: str) -> SkillResult:
        report = validate_form(spec, md)
        if report.blocking:
            await emit.block(blocks.markdown("This form still has validation errors and can't be deployed:"))
            await emit.block(blocks.validation_report(report))
            return _persist(spec, "preview")

        plan = await build_deployment_plan(ctx.tool_ctx, spec, environment_name=ctx.environment_name,
                                           classification=ctx.classification, demo=ctx.demo)

        if phase != "awaiting_approval":
            await emit.block(blocks.deployment_plan(plan))
            prod = ctx.classification == "production"
            actions = [
                blocks.action("confirm", f"Deploy to {ctx.environment_name}",
                              f"confirm deploy {spec.name}" if prod else "confirm deploy", "danger" if prod else "primary"),
                blocks.action("edit", "Edit", "edit"),
                blocks.action("download", "Download only", "download only"),
                blocks.action("cancel", "Cancel", "cancel", "ghost"),
            ]
            detail = None
            if prod:
                detail = f"PRODUCTION deployment. Type: confirm deploy {spec.name}"
            await emit.block(blocks.confirmation(
                f"Ready to deploy **{spec.name}** to **{ctx.environment_name}** ({ctx.classification}).",
                actions, detail=detail, severity="warning" if prod else "info"))
            return _persist(spec, "awaiting_approval", FormWorkflowState.awaiting_approval)

        # awaiting_approval + confirmation -> execute
        if ctx.classification == "production" and spec.name.lower() not in text.lower():
            await emit.block(blocks.markdown(
                f"Production safeguard: please confirm by typing **confirm deploy {spec.name}**."))
            return _persist(spec, "awaiting_approval")

        emit.set_steps(blocks.steps("Building artifact", "Deploying to Oracle", "Verifying"))
        await emit.step_running(0)
        progress = blocks.deployment_progress(plan)
        await emit.block(progress)

        async def on_step(updated_plan):
            progress.data = updated_plan.model_dump(by_alias=True)
            await emit.block(progress)

        await emit.step_done(0)
        await emit.step_running(1)
        deploy_report = await execute_deployment(
            ctx.tool_ctx, spec, plan, demo=ctx.demo, conversation_id=ctx.conversation.id,
            approval_note=text[:200], on_step=on_step)
        await emit.step_done(1)
        await emit.step_running(2)
        await emit.step_done(2)

        await emit.block(blocks.deployment_result(deploy_report))
        if deploy_report.verified:
            await emit.prose(f"✅ **{spec.name}** was deployed and verified"
                             + (" (demo — no Oracle tenant was changed)." if ctx.demo else ".") + "\n")
        elif deploy_report.success:
            await emit.prose("Import completed, but verification is incomplete. See the report above.")
        else:
            await emit.prose("The deployment did not succeed. See the errors above; you can edit and retry.")
        state = deploy_report.state
        active = state not in (FormWorkflowState.completed, FormWorkflowState.cancelled)
        return SkillResult(skill="forms", workflow_state=state.value if hasattr(state, "value") else str(state),
                           workflow_data={"spec": spec.model_dump(by_alias=True), "phase": "done"},
                           workflow_active=active)


def _ct(name: str):
    from ...schemas.chat import ChatBlockType
    return ChatBlockType(name)


async def _retrieve_grounding(ctx: SkillContext, *, kinds: list[str], k: int) -> list[dict]:
    """Best-effort RAG grounding chunks for the current request (spec: RAG feature).

    Retrieval is a garnish on artifact creation, never a gate: no active context
    version means no grounding, and any retrieval failure (module not deployed,
    index rebuild error, provider hiccup) silently yields no chunks rather than
    breaking the creation flow.
    """
    if not ctx.context_version_id:
        return []
    try:
        from ...rag import retrieve_grounding
        chunks = await retrieve_grounding(ctx.session, ctx.context_version_id, ctx.user_text,
                                          kinds=kinds, k=k, provider=ctx.provider)
        return [c.model_dump(by_alias=True) for c in chunks]
    except Exception:
        return []


def _grounding_block(query: str, purpose: str, chunks: list[dict]):
    """``groundingSources`` block, or None when there is nothing worth showing.
    Defensive for the same reason as :func:`_retrieve_grounding`."""
    if not chunks:
        return None
    try:
        return blocks.grounding_sources({"query": query, "purpose": purpose, "chunks": chunks})
    except Exception:
        return None


def _load_spec(wf) -> FormSpecification | None:
    if wf and wf.data and wf.data.get("spec"):
        try:
            return FormSpecification.model_validate(wf.data["spec"])
        except Exception:
            return None
    return None


def _persist(spec: FormSpecification, phase: str, state: FormWorkflowState | None = None) -> SkillResult:
    return SkillResult(
        skill="forms",
        workflow_state=(state.value if state else FormWorkflowState.preview_ready.value),
        workflow_data={"spec": spec.model_dump(by_alias=True), "phase": phase},
        workflow_active=True,
    )


def _short_json(spec: FormSpecification) -> str:
    import json
    d = spec.model_dump(by_alias=True, exclude_none=True)
    return json.dumps({k: d[k] for k in ("pov", "pages", "rows", "columns", "display", "businessRuleAssociations")
                       if k in d}, indent=2)
