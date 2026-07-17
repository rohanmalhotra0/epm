"""/context skill — build, refresh, export context (spec sections 16-18)."""

from __future__ import annotations

from ...context import build_context, diff_contexts, export_context_package
from ...context.engine import environment_fingerprint
from ...schemas.tools import SkillSpec
from ...services import artifacts as artifacts_svc
from ...services import context_store, environments
from .. import blocks
from .base import Emitter, Skill, SkillContext, SkillResult


class ContextSkill(Skill):
    spec = SkillSpec(name="/context", description="Learn or refresh the connected EPM application.",
                     intent_examples=["build context", "learn this application", "refresh context"])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        tl = ctx.user_text.lower()
        if "export" in tl:
            return await self._export(ctx, emit)
        if "refresh" in tl:
            return await self._build(ctx, emit, refresh=True)
        mode = "deep" if "deep" in tl else "quick"
        return await self._build(ctx, emit, mode=mode)

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
        filename, data = export_context_package(ctx.session, cv.id)
        from ...config import get_settings
        path = get_settings().contexts_dir / filename
        path.write_bytes(data)
        artifact = artifacts_svc.save_artifact(ctx.session, ctx.project.id, "contextPackage", filename,
                                               path=str(path), metadata={"sizeBytes": len(data)})
        ctx.session.flush()
        await emit.prose(f"Exported the active context as **{filename}** ({len(data):,} bytes).\n\n")
        await emit.block(blocks.downloadable_file({
            "filename": filename, "artifactId": artifact.id, "mediaType": "application/zip", "sizeBytes": len(data),
        }))
        return SkillResult(skill="context")


def _fmt_counts(counts: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in sorted(counts.items()))
