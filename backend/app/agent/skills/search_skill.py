"""/search skill — deterministic metadata answers (spec sections 19, 35)."""

from __future__ import annotations

import re

from ...schemas.tools import SkillSpec
from .. import blocks
from ..form_nlu import find_member
from .base import Emitter, Skill, SkillContext, SkillResult


class SearchSkill(Skill):
    spec = SkillSpec(name="/search", description="Find members, forms, rules and variables.",
                     intent_examples=["what cubes exist", "search members", "list forms"])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        text = ctx.user_text
        tl = text.lower()
        md = await ctx.tool_ctx.metadata()

        emit.set_steps(blocks.steps("Understanding request", "Searching EPM context"))
        await emit.step_running(0)
        await emit.step_done(0)
        await emit.step_running(1)

        if re.search(r"\bcube", tl) and re.search(r"\bdimension", tl):
            await self._cubes_and_dims(emit, md)
        elif re.search(r"\bcube", tl):
            await self._cubes(emit, md)
        elif re.search(r"\bdimension", tl):
            await self._dimensions(emit, md)
        elif re.search(r"\bform", tl):
            await self._forms(emit, md)
        elif re.search(r"\brule", tl):
            await self._rules(emit, md)
        elif re.search(r"\bvariable", tl):
            await self._variables(emit, md)
        else:
            await self._members(emit, md, text)

        await emit.step_done(1)
        return SkillResult(skill="search")

    async def _cubes_and_dims(self, emit, md):
        lines = [f"**{md.application}** has {len(md.cubes)} cubes and {len(md.dimensions)} dimensions.", ""]
        for c in md.cubes.values():
            lines.append(f"- **{c.name}** ({c.type}) — {len(c.dimensions)} dims: {', '.join(c.dimensions)}")
        await emit.block(blocks.markdown("\n".join(lines)))

    async def _cubes(self, emit, md):
        lines = [f"**{md.application}** has {len(md.cubes)} cubes:", ""]
        lines += [f"- **{c.name}** ({c.type}) — {c.description or ''}" for c in md.cubes.values()]
        await emit.block(blocks.markdown("\n".join(lines)))

    async def _dimensions(self, emit, md):
        lines = [f"**{md.application}** dimensions ({len(md.dimensions)}):", "",
                 "| Dimension | Type | Cubes |", "|---|---|---|"]
        for d in md.dimensions.values():
            cubes = [c.name for c in md.cubes.values() if d.name in c.dimensions]
            lines.append(f"| {d.name} | {d.type} | {', '.join(cubes)} |")
        await emit.block(blocks.markdown("\n".join(lines)))

    async def _forms(self, emit, md):
        if not md.forms:
            await emit.block(blocks.markdown("No forms are available in the current context."))
            return
        lines = ["Forms:", "", "| Form | Cube | Folder |", "|---|---|---|"]
        lines += [f"| {f.name} | {f.cube or ''} | {f.folder or ''} |" for f in md.forms.values()]
        await emit.block(blocks.markdown("\n".join(lines)))

    async def _rules(self, emit, md):
        lines = ["Business rules:", "", "| Rule | Cube | Type | Runtime prompts |", "|---|---|---|---|"]
        for r in md.rules.values():
            lines.append(f"| {r.name} | {r.cube or ''} | {r.type} | {', '.join(r.runtime_prompts) or '—'} |")
        await emit.block(blocks.markdown("\n".join(lines)))

    async def _variables(self, emit, md):
        lines = ["Variables:", "", "| Variable | Scope | Dimension | Value |", "|---|---|---|---|"]
        for v in md.variables.values():
            lines.append(f"| {v.name} | {v.scope} | {v.dimension or ''} | {v.value or ''} |")
        await emit.block(blocks.markdown("\n".join(lines)))

    async def _members(self, emit, md, text):
        query = text
        found = find_member(md, text)
        matches = []
        for dim, members in md.members.items():
            for m in members.values():
                if query.lower() in m.name.lower() or (m.alias and query.lower() in m.alias.lower()):
                    matches.append({"member": m.name, "alias": m.alias, "dimension": dim,
                                    "parent": m.parent, "confidence": "exact" if m.name.lower() == query.lower() else "medium",
                                    "retrievalMethod": "substring"})
        matches = matches[:25]
        if found:
            await emit.block(blocks.markdown(
                f"I matched **{query}** to technical member **{found[0]}** in dimension **{found[1]}**."))
        await emit.block(blocks.member_search_results(query, matches))
