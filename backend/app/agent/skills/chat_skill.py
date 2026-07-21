"""Free-chat fallback — streams provider text, grounded with light context."""

from __future__ import annotations

from ...ai.base import AIMessage
from ...schemas.tools import SkillSpec
from ..grounding import _fence_excerpts
from .base import Emitter, Skill, SkillContext, SkillResult
from .forms_skill import _grounding_block, _retrieve_grounding


class ChatSkill(Skill):
    spec = SkillSpec(name="/chat", description="General conversation.", intent_examples=[])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        summary = (f"Active application: {md.application}. Cubes: {', '.join(md.cubes)}. "
                   f"Dimensions: {', '.join(md.dimensions)}.")
        system = (
            "You are EPM Wizard, a local-first assistant for Oracle EPM implementation. "
            "Be concise and factual. Only reference members, cubes and rules that exist in the "
            f"provided context. {summary} "
            "For building forms, running rules, or visualizing cube architecture, tell the user to "
            "use the matching skill (/forms, /rules, /architecture)."
        )
        # RAG grounding is a garnish, never a gate: the helpers are defensive,
        # so any retrieval failure yields no chunks and chat proceeds ungrounded.
        grounding = await _retrieve_grounding(ctx, kinds=None, k=4)
        if grounding:
            if (grounding_block := _grounding_block(ctx.user_text, "chat", grounding)) is not None:
                await emit.block(grounding_block)
            if (fenced := _fence_excerpts(grounding, 3000)) is not None:
                system = f"{system}\n\n{fenced}"
        await emit.stream_provider_text(ctx, [AIMessage(role="user", content=ctx.user_text)], system=system)
        usage = emit.usage if any(emit.usage.values()) else None
        return SkillResult(skill="chat", provider_used=ctx.provider.name,
                           model_used=ctx.provider.config.default_model, usage=usage)
