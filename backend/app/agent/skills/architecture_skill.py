"""Cube Architecture & Dimensionality Visualizer skill (spec 4B).

Deterministic: the model may route here and narrate, but every number/dimension
comes from real metadata via the architecture service.
"""

from __future__ import annotations

from ...architecture import service as arch
from ...schemas.form_spec import FormSpecification
from ...schemas.tools import SkillSpec
from .. import blocks
from ..form_nlu import find_member
from .base import Emitter, Skill, SkillContext, SkillResult

_ACTIONS = [
    ("cell", "Explain one cell", "explain one cell"),
    ("coverage", "Show form coverage", "show form coverage"),
    ("compare", "Compare cubes", "compare cubes"),
    ("hierarchy", "Show hierarchy", "inspect Account hierarchy"),
]


class ArchitectureSkill(Skill):
    spec = SkillSpec(
        name="/architecture",
        description="Visualize a cube's dimensions and how a form uses them.",
        intent_examples=["visualize OEP_DCSH", "what dimensions are in this cube",
                         "explain one cell", "compare cubes", "which dimensions am I missing"],
    )

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        md = await ctx.tool_ctx.metadata()
        text = ctx.user_text
        tl = text.lower()
        spec = ctx.active_form_spec if isinstance(ctx.active_form_spec, FormSpecification) else None
        cubes_in_text = [c for c in md.cubes if c.lower() in tl]

        emit.set_steps(blocks.steps("Understanding request", "Retrieving cube metadata", "Building visualization"))
        await emit.step_running(0)
        await emit.step_done(0)
        await emit.step_running(1)

        if len(cubes_in_text) >= 2 or (("compare" in tl or " vs " in tl) and cubes_in_text):
            await self._compare(emit, md, cubes_in_text)
        elif any(k in tl for k in ("cell", "intersection", "identifies", "makes up", "data cell")):
            await self._cell(emit, md, spec, cubes_in_text)
        elif any(k in tl for k in ("coverage", "missing", "how this form", "how my form", "dimensionality of")):
            await self._coverage(emit, md, spec, cubes_in_text)
        elif ("hierarchy" in tl or "inspect" in tl):
            await self._hierarchy(emit, md, text)
        else:
            await self._architecture(emit, md, spec, cubes_in_text)

        await emit.step_done(1)
        await emit.step_done(2)
        return SkillResult(skill="architecture")

    def _pick_cube(self, md, spec, cubes_in_text) -> str:
        if cubes_in_text:
            return cubes_in_text[0]
        if spec is not None:
            return spec.cube
        return next(iter(md.cubes), "OEP_FS")

    async def _architecture(self, emit, md, spec, cubes_in_text):
        cube = self._pick_cube(md, spec, cubes_in_text)
        use_spec = spec if (spec and spec.cube == cube) else None
        model = arch.get_cube_architecture(md, cube, use_spec)
        await emit.step_running(2)
        await emit.prose(
            f"**{model.application} · {cube}** has {model.dimension_count} dimensions. "
            f"A value in this cube is identified by selecting one member from every dimension.\n\n")
        await emit.block(blocks._block(_ct("cubeArchitecture"), model.model_dump(by_alias=True)))
        await emit.block(blocks.markdown(_dimension_table(cube, model)))
        if use_spec is None:
            cell = arch.explain_cell_intersection(md, cube)
            await emit.block(blocks._block(_ct("cellIntersection"), cell.model_dump(by_alias=True)))
        await self._actions(emit, cube)

    async def _coverage(self, emit, md, spec, cubes_in_text):
        if spec is None:
            await emit.block(blocks.markdown(
                "There's no form in progress. Start one with `/forms` and I'll show how it covers the cube."))
            return
        cube = spec.cube
        model = arch.get_cube_architecture(md, cube, spec)
        report = arch.validate_dimension_coverage(md, cube, spec)
        size = arch.cross_dimensional_size(md, cube, spec)
        await emit.step_running(2)
        await emit.block(blocks._block(_ct("cubeArchitecture"), model.model_dump(by_alias=True)))
        await emit.block(blocks.markdown(_coverage_table(spec, model)))
        await emit.block(blocks._block(_ct("dimensionCoverage"), report.model_dump(by_alias=True)))
        await emit.block(blocks.markdown(_size_table(size)))
        await self._actions(emit, cube)

    async def _cell(self, emit, md, spec, cubes_in_text):
        cube = self._pick_cube(md, spec, cubes_in_text)
        use_spec = spec if (spec and spec.cube == cube) else None
        cell = arch.explain_cell_intersection(md, cube, spec=use_spec)
        await emit.step_running(2)
        await emit.prose("An EPM cell is the intersection of one member from **every** cube dimension:\n\n")
        await emit.block(blocks.markdown(_cell_table(cell)))
        await emit.block(blocks._block(_ct("cellIntersection"), cell.model_dump(by_alias=True)))

    async def _compare(self, emit, md, cubes_in_text):
        a, b = cubes_in_text[0], cubes_in_text[1] if len(cubes_in_text) > 1 else next(iter(md.cubes))
        cmp = arch.compare_cubes(md, a, b)
        await emit.step_running(2)
        await emit.block(blocks.markdown(_compare_table(cmp)))
        await emit.block(blocks._block(_ct("cubeComparison"), cmp.model_dump(by_alias=True)))

    async def _hierarchy(self, emit, md, text):
        dim = next((d for d in md.dimensions if d.lower() in text.lower()), "Account")
        member = find_member(md, text, dimension=dim)
        root = member[0] if member else None
        h = arch.inspect_dimension_hierarchy(md, dim, root=root, cap=50)
        await emit.step_running(2)
        await emit.block(blocks._block(_ct("dimensionHierarchy"), h.model_dump(by_alias=True)))

    async def _actions(self, emit, cube):
        acts = [blocks.action(k, label, value) for k, label, value in _ACTIONS]
        acts.insert(0, blocks.action("inspect", "Inspect dimension", "inspect Account hierarchy", "secondary"))
        await emit.block(blocks.confirmation(f"Explore {cube} further:", acts))


def _ct(name: str):
    from ...schemas.chat import ChatBlockType
    return ChatBlockType(name)


def _dimension_table(cube: str, model) -> str:
    lines = [f"### {cube} dimensions", "",
             "| Dimension | Purpose | Members | Form placement | Current selection |",
             "|---|---|---:|---|---|"]
    for d in model.dimensions:
        purpose = arch.dimension_purpose(d.type, d.name)
        placement = d.used_on_axis.upper() if d.used_on_axis else ("Not assigned" if model.form_coverage else "—")
        sel = d.selection_summary or d.selected_member or "—"
        count = d.member_count if d.member_count is not None else "—"
        lines.append(f"| {d.name} | {purpose} | {count} | {placement} | {sel} |")
    return "\n".join(lines)


def _coverage_table(spec, model) -> str:
    lines = ["### How this form uses the cube", "",
             "| Cube dimension | Form role | Selection |", "|---|---|---|"]
    for d in model.dimensions:
        role = d.used_on_axis.upper() if d.used_on_axis else "Missing"
        sel = d.selection_summary or d.selected_member or "Not selected"
        lines.append(f"| {d.name} | {role} | {sel} |")
    return "\n".join(lines)


def _cell_table(cell) -> str:
    lines = ["### What identifies this cell?", "", "| Dimension | Member |", "|---|---|"]
    for m in cell.members:
        lines.append(f"| {m.dimension} | {m.member} |")
    lines += ["", "```", cell.expression, "```"]
    return "\n".join(lines)


def _compare_table(cmp) -> str:
    lines = [f"### {cmp.cube_a} vs {cmp.cube_b}", "",
             f"| Dimension | {cmp.cube_a} | {cmp.cube_b} |", "|---|:--:|:--:|"]
    for r in cmp.rows:
        lines.append(f"| {r.dimension} | {'Yes' if r.in_a else 'No'} | {'Yes' if r.in_b else 'No'} |")
    lines += ["", f"**Shared dimensions:** {cmp.shared}",
              f"**Only in {cmp.cube_a}:** {', '.join(cmp.only_a) or '—'}",
              f"**Only in {cmp.cube_b}:** {', '.join(cmp.only_b) or '—'}"]
    return "\n".join(lines)


def _size_table(size) -> str:
    lines = ["### Form dimensionality", "", "| Area | Combination |", "|---|---:|"]
    for a in size.areas:
        lines.append(f"| {a.area.title()} | {a.detail} |")
    lines.append(f"| **Total potential cells** | **{size.total_potential_cells:,}** |")
    lines.append("")
    lines.append(f"_{size.label}._" + (f" ⚠️ {size.warning}" if size.warning else ""))
    return "\n".join(lines)
