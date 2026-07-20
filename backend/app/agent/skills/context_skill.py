"""/context skill — build, refresh, export context and import LCM application
snapshots (spec sections 16-18)."""

from __future__ import annotations

import re
from pathlib import Path

from ...context import build_context, diff_contexts
from ...context.engine import environment_fingerprint
from ...context.report_docx import DOCX_MIME as _DOCX_MIME
from ...context.report_docx import build_context_docx
from ...db.models import Attachment
from ...schemas.tools import SkillSpec
from ...services import artifacts as artifacts_svc
from ...services import attachments as attachments_svc
from ...services import context_store, environments
from .. import blocks
from .base import Emitter, Skill, SkillContext, SkillResult

# Optional trailing token = the attachment id a confirmation action was bound to.
_SNAPSHOT_CMD = re.compile(r"\b(merge|import)\s+snapshot\b(?:\s+([\w-]+))?", re.IGNORECASE)


class ContextSkill(Skill):
    spec = SkillSpec(name="/context",
                     description="Learn or refresh the connected EPM application, "
                                 "or import an LCM application snapshot zip.",
                     intent_examples=["build context", "learn this application", "refresh context"])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        tl = ctx.user_text.lower()
        if ctx.attachment_ids:
            zips = self._zip_attachments(ctx)
            if zips:
                return await self._snapshot_uploaded(ctx, emit, zips[0], extra=len(zips) - 1)
        if (m := _SNAPSHOT_CMD.search(ctx.user_text)) is not None:
            return await self._snapshot_import(ctx, emit, standalone=m.group(1).lower() == "import",
                                               attachment_id=m.group(2))
        if "export" in tl:
            return await self._export(ctx, emit)
        if "refresh" in tl:
            return await self._build(ctx, emit, refresh=True)
        return await self._build(ctx, emit)

    async def _build(self, ctx: SkillContext, emit: Emitter, mode: str = "quick", refresh: bool = False) -> SkillResult:
        emit.set_steps(blocks.steps("Understanding request", "Retrieving metadata", "Indexing context", "Saving version"))
        await emit.step_running(0)
        await emit.step_done(0)
        await emit.step_running(1)

        fp = environment_fingerprint(getattr(ctx.connector.info, "application", None), ctx.application, None)
        bundle = await build_context(ctx.connector, ctx.application, mode=mode, fingerprint=fp)
        await emit.step_done(1)
        await emit.step_running(2)

        prev = context_store.get_active_context(ctx.session, ctx.project.id)
        context_store.persist_context(
            ctx.session, ctx.project.id, bundle.application, bundle.mode, bundle.label,
            bundle.manifest.model_dump(by_alias=True), bundle.counts, bundle.records,
            fingerprint=bundle.fingerprint,
        )
        ctx.session.flush()
        if ctx.project.active_environment_id:
            environments.mark_context_refreshed(ctx.session, ctx.project.active_environment_id)
        await emit.step_done(2)
        await emit.step_running(3)
        await emit.step_done(3)

        await emit.prose(
            f"Context **{bundle.mode}** built for **{ctx.application}**: "
            f"{bundle.counts['cubes']} cubes, {bundle.counts['dimensions']} dimensions, "
            f"{bundle.counts['members']} members, {bundle.counts['forms']} forms, "
            f"{bundle.counts['rules']} rules, {bundle.counts['variables']} variables.\n\n"
        )
        await emit.block(blocks.context_summary({
            "application": bundle.application,
            "mode": bundle.mode,
            "label": bundle.label,
            "counts": bundle.counts,
            "sections": [s.model_dump(by_alias=True) for s in bundle.sections],
            "active": True,
        }))

        if refresh and prev is not None:
            d = diff_contexts(prev.counts or {}, bundle.counts)
            changed = {k: v for k, v in d.items() if v["delta"] != 0}
            await emit.block(blocks.diff("Context changes", _fmt_counts(prev.counts or {}),
                                         _fmt_counts(bundle.counts), language="text"))
            if not changed:
                await emit.prose("No count-level changes since the previous version.")

        return SkillResult(skill="context")

    async def _export(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        cv = context_store.get_active_context(ctx.session, ctx.project.id)
        if cv is None:
            await emit.block(blocks.markdown("No active context to export. Build one first with `/context build`."))
            return SkillResult(skill="context")
        filename, data = build_context_docx(ctx.session, cv.id)
        from ...config import get_settings
        path = get_settings().contexts_dir / filename
        path.write_bytes(data)
        artifact = artifacts_svc.save_artifact(ctx.session, ctx.project.id, "contextPackage", filename,
                                               path=str(path), metadata={"sizeBytes": len(data)})
        ctx.session.flush()
        await emit.prose(f"Exported the active context as **{filename}** ({len(data):,} bytes).\n\n")
        await emit.block(blocks.downloadable_file({
            "filename": filename, "artifactId": artifact.id, "mediaType": _DOCX_MIME, "sizeBytes": len(data),
        }))
        return SkillResult(skill="context")

    # --- LCM snapshot zips ----------------------------------------------------

    def _zip_attachments(self, ctx: SkillContext) -> list[Attachment]:
        rows = [attachments_svc.get_attachment(ctx.session, aid) for aid in ctx.attachment_ids]
        return [a for a in rows if a is not None and (
            a.media_type == attachments_svc.ZIP_MEDIA_TYPE or a.filename.lower().endswith(".zip"))]

    def _latest_zip(self, ctx: SkillContext) -> Attachment | None:
        return (ctx.session.query(Attachment)
                .filter(Attachment.conversation_id == ctx.conversation.id,
                        Attachment.filename.ilike("%.zip"))
                .order_by(Attachment.created_at.desc(), Attachment.id.desc())
                .first())

    async def _snapshot_uploaded(self, ctx: SkillContext, emit: Emitter,
                                 attachment: Attachment, extra: int = 0) -> SkillResult:
        """An LCM snapshot zip arrived: present the analysis, then either offer
        merge/standalone (an active context exists) or import standalone now."""
        analysis = attachments_svc.load_snapshot_analysis(attachment)
        await emit.block(blocks.snapshot_summary(
            analysis.model_dump(by_alias=True) | {"filename": attachment.filename}))
        if extra:
            await emit.block(blocks.markdown(
                f"_{extra} further zip attachment(s) were ignored — snapshots are applied one at a time._"))
        if context_store.get_active_context(ctx.session, ctx.project.id) is None:
            return await self._snapshot_import(ctx, emit, standalone=True, attachment=attachment)
        prompt = (f"**{attachment.filename}** parsed as an application snapshot"
                  + (f" of **{analysis.application}**" if analysis.application else "")
                  + ". How should it be applied?")
        # The attachment id rides in the action value so the confirmation always
        # acts on the zip it summarized, not whichever zip is newest by then.
        await emit.block(blocks.confirmation(prompt, [
            blocks.action("merge", "Merge onto active context",
                          f"/context merge snapshot {attachment.id}", "primary"),
            blocks.action("standalone", "Import as standalone context",
                          f"/context import snapshot {attachment.id}"),
            blocks.action("cancel", "Cancel", "cancel", "ghost"),
        ]))
        return SkillResult(skill="context")

    async def _snapshot_import(self, ctx: SkillContext, emit: Emitter, *, standalone: bool,
                               attachment: Attachment | None = None,
                               attachment_id: str | None = None) -> SkillResult:
        # Runtime import: the snapshot parser lives with the context engine.
        from ...context.snapshot import SnapshotError, analyze_snapshot, merge_snapshot_into_context

        if attachment is None and attachment_id:
            candidate = attachments_svc.get_attachment(ctx.session, attachment_id)
            if candidate is not None and candidate.conversation_id == ctx.conversation.id \
                    and candidate.filename.lower().endswith(".zip"):
                attachment = candidate
        attachment = attachment or self._latest_zip(ctx)
        if attachment is None:
            await emit.block(blocks.markdown(
                "There's no snapshot zip in this conversation. Attach an LCM application "
                "snapshot (the `.zip` from `epmautomate exportSnapshot`) with the paperclip, "
                "then say *merge snapshot* or *import snapshot*."))
            return SkillResult(skill="context")

        emit.set_steps(blocks.steps("Reading snapshot", "Parsing artifacts",
                                    "Merging context", "Saving version"))
        await emit.step_running(0)
        data = Path(attachment.path).read_bytes()
        await emit.step_done(0)
        await emit.step_running(1)
        try:
            bundle = analyze_snapshot(data, attachment.filename)
        except SnapshotError as exc:
            await emit.block(blocks.markdown(
                f"**{attachment.filename}** could not be parsed as an LCM snapshot: {exc}"))
            return SkillResult(skill="context")
        await emit.step_done(1)

        await emit.step_running(2)
        active_before = context_store.get_active_context(ctx.session, ctx.project.id)
        before_counts = dict(active_before.counts or {}) if active_before else {}
        cv = merge_snapshot_into_context(ctx.session, ctx.project.id, bundle,
                                         standalone=standalone, filename=attachment.filename)
        ctx.session.flush()
        await emit.step_done(2)
        await emit.step_running(3)
        await emit.step_done(3)

        merged = cv.mode == "hybrid"
        applied = (f"merged onto **{active_before.label}**" if merged and active_before
                   else "imported as a standalone context")
        await emit.prose(
            f"Snapshot **{attachment.filename}** {applied}: new context version "
            f"**{cv.label}** (mode `{cv.mode}`) is now active.\n\n")
        manifest = cv.manifest or {}
        await emit.block(blocks.context_summary({
            "application": cv.application,
            "mode": cv.mode,
            "label": cv.label,
            "counts": cv.counts or {},
            "sections": manifest.get("sections", []),
            "active": True,
        }))
        upgraded = manifest.get("mergedSections") or [s.name for s in bundle.sections]
        await emit.block(blocks.markdown(
            "**Sections upgraded by the snapshot:**\n\n" + "\n".join(f"- {u}" for u in upgraded)))
        if merged:
            await emit.block(blocks.diff("Context changes", _fmt_counts(before_counts),
                                         _fmt_counts(cv.counts or {}), language="text"))
        return SkillResult(skill="context")


def _fmt_counts(counts: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in sorted(counts.items()))
