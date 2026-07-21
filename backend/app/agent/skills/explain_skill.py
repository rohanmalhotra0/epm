"""/explain skill — explain a rule or a calculation (spec section 31)."""

from __future__ import annotations

import re

from ...ai.base import AIMessage
from ...connector.demo import DemoConnector
from ...schemas.tools import SkillSpec
from .. import blocks
from ..form_nlu import _match_rule, find_member
from ..grounding import _fence_excerpts
from .base import Emitter, Skill, SkillContext, SkillResult
from .forms_skill import _grounding_block, _retrieve_grounding


class ExplainSkill(Skill):
    spec = SkillSpec(name="/explain", description="Explain a rule or calculation.",
                     intent_examples=["explain the IR rule", "explain a calculation"])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        text = ctx.user_text

        # Additive RAG grounding (never a gate): provenance block before the
        # explanation, excerpts fenced into any provider prompt. The helpers
        # are defensive — a retrieval failure simply means no grounding.
        grounding = await _retrieve_grounding(
            ctx, kinds=["rule", "template", "form", "member", "variable"], k=4)
        grounding_block = _grounding_block(text, "explain", grounding)

        # rule phrase after "explain"
        m = re.search(r"explain\s+(the\s+)?([\w \-]+?)\s+rule\b", text, re.I)
        rule_name = _match_rule(md, m.group(2)) if m else _match_rule(md, text)
        if rule_name:
            if grounding_block is not None:
                await emit.block(grounding_block)
            return await self._explain_rule(ctx, emit, rule_name)

        member = find_member(md, text)
        if member:
            mrec = md.get_member(member[1], member[0])
            if mrec and mrec.formula:
                if grounding_block is not None:
                    await emit.block(grounding_block)
                await emit.block(blocks.markdown(
                    f"### {mrec.name}\n\n**Type:** {mrec.storage}\n\n**Formula:**"))
                await emit.block(blocks.code(mrec.formula, "text"))
                await emit.prose("This is a calculated member; its value is derived from the formula above rather than stored.")
                return SkillResult(skill="explain")

        # fall back to the provider for open-ended explanation
        if grounding_block is not None:
            await emit.block(grounding_block)
        system = ("You are EPM Wizard. Explain the user's EPM question concisely and factually. "
                  "Do not invent tenant-specific members or values.")
        if (fenced := _fence_excerpts(grounding, 3000)) is not None:
            system = f"{system}\n\n{fenced}"
        await emit.stream_provider_text(ctx, [AIMessage(role="user", content=text)], system=system)
        return SkillResult(skill="explain", provider_used=ctx.provider.name)

    async def _explain_rule(self, ctx: SkillContext, emit: Emitter, rule_name: str) -> SkillResult:
        emit.set_steps(blocks.steps("Understanding request", "Reading rule source"))
        await emit.step_running(0)
        await emit.step_done(0)
        await emit.step_running(1)

        raw = ctx.connector.get_rule_raw(rule_name) if isinstance(ctx.connector, DemoConnector) else None
        rule = await ctx.connector.get_rule(ctx.application, rule_name)
        await emit.step_done(1)
        if rule is None:
            await emit.block(blocks.markdown(f"I couldn't find a rule named **{rule_name}**."))
            return SkillResult(skill="explain")

        purpose = (raw or {}).get("purpose")
        source = (raw or {}).get("source")
        prompts = (raw or {}).get("prompt_defs", [])
        lines = [f"### {rule.name}", ""]
        lines.append("**Facts (from rule metadata):**")
        lines.append(f"- Cube: {rule.cube or 'unknown'}")
        lines.append(f"- Type: {rule.type}")
        if rule.runtime_prompts:
            lines.append(f"- Runtime prompts: {', '.join(rule.runtime_prompts)}")
        if purpose:
            lines += ["", f"**Purpose (documented):** {purpose}"]
        if prompts:
            lines += ["", "**Runtime prompts:**", "", "| Prompt | Type | Default |", "|---|---|---|"]
            for p in prompts:
                lines.append(f"| {p['name']} | {p.get('type','text')} | {p.get('default','—')} |")
        await emit.block(blocks.markdown("\n".join(lines)))
        if source:
            await emit.block(blocks.markdown("**Main calculation (from source):**"))
            await emit.block(blocks.code(source, "java" if rule.type == "groovy" else "text"))
        await emit.block(blocks.markdown(
            "_Facts above come from the rule source and context. Business meaning beyond the "
            "documented purpose is not asserted._"))
        return SkillResult(skill="explain")
