"""/compare skill — compare two cubes or context versions."""

from __future__ import annotations

from ...architecture import service as arch
from ...schemas.tools import SkillSpec
from ...services import context_store
from .. import blocks
from .architecture_skill import _compare_table, _ct
from .base import Emitter, Skill, SkillContext, SkillResult


class CompareSkill(Skill):
    spec = SkillSpec(name="/compare", description="Compare two cubes or two context versions.",
                     intent_examples=["compare OEP_DCSH and OEP_FS", "compare context versions"])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        tl = ctx.user_text.lower()
        cubes = [c for c in md.cubes if c.lower() in tl]
        if len(cubes) >= 2:
            cmp = arch.compare_cubes(md, cubes[0], cubes[1])
            await emit.block(blocks.markdown(_compare_table(cmp)))
            await emit.block(blocks._block(_ct("cubeComparison"), cmp.model_dump(by_alias=True)))
            return SkillResult(skill="compare")

        if "context" in tl:
            versions = context_store.list_context_versions(ctx.session, ctx.project.id)
            if len(versions) < 2:
                await emit.block(blocks.markdown("You need at least two context versions to compare. "
                                                 "Run `/context refresh` to create a new one."))
                return SkillResult(skill="compare")
            a, b = versions[0], versions[1]
            await emit.block(blocks.diff(f"{b.label} → {a.label}",
                                         _fmt(b.counts or {}), _fmt(a.counts or {}), language="text"))
            return SkillResult(skill="compare")

        await emit.block(blocks.markdown("Name two cubes to compare, e.g. *compare OEP_DCSH and OEP_FS*, "
                                         "or say *compare context versions*."))
        return SkillResult(skill="compare")


def _fmt(counts: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in sorted(counts.items()))
