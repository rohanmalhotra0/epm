"""Deterministic Cube Architecture services (spec 4B).

Every function derives its output from real tenant metadata (``TenantMetadata``
built from the connector or the active context). The LLM may decide a
visualization is wanted and narrate the result, but never invents the data.
"""

from __future__ import annotations

from ..artifacts.metadata import TenantMetadata
from ..artifacts.resolver import ResolutionError, resolve_selection
from ..schemas.architecture import (
    CellIntersection,
    CellMember,
    CrossDimArea,
    CrossDimSize,
    CubeArchitecture,
    CubeComparison,
    CubeComparisonRow,
    DimensionCoverageReport,
    DimensionHierarchy,
    DimensionNode,
    FormCoverage,
    HierarchyNode,
    MissingSuggestion,
)
from ..schemas.form_spec import FormSpecification
from ..schemas.validation import SizeEstimate

_STANDARD_TYPES = {"account", "entity", "scenario", "version", "period", "years", "currency"}

_GROUPS = {
    "period": "time", "years": "time",
    "scenario": "context", "version": "context",
    "entity": "organization",
    "account": "financial", "currency": "financial",
}
_NAME_GROUP_HINTS = {
    "business unit": "organization", "cost center": "organization",
    "bank": "custom", "party": "custom", "forecast method": "custom",
    "line item": "custom", "category": "custom",
}
_DIM_PURPOSE = {
    "account": "Financial line", "entity": "Organization", "scenario": "Planning scenario",
    "version": "Data version", "period": "Time period", "years": "Fiscal year",
    "currency": "Reporting currency",
}


def classify_dimension(dim_type: str, name: str) -> tuple[str, str]:
    """Return (display_type, group). Unknown -> 'custom', never guessed."""
    t = (dim_type or "generic").lower()
    display = t if t in _STANDARD_TYPES else "custom"
    group = _GROUPS.get(t)
    if group is None:
        group = _NAME_GROUP_HINTS.get(name.lower(), "custom")
    return display, group


def dimension_purpose(dim_type: str, name: str) -> str:
    display, _ = classify_dimension(dim_type, name)
    return _DIM_PURPOSE.get(display, "Custom dimension")


def _root_members(md: TenantMetadata, dimension: str) -> list[str]:
    return [m.name for m in md.members.get(dimension, {}).values() if not m.parent]


def _axis_placement(spec: FormSpecification | None, dimension: str):
    if spec is None:
        return None, None
    for kind, axis in (("pov", spec.pov), ("pages", spec.pages), ("rows", spec.rows), ("columns", spec.columns)):
        for am in axis:
            if am.dimension == dimension:
                return kind, am
    return None, None


def get_cube_architecture(
    md: TenantMetadata, cube: str, spec: FormSpecification | None = None
) -> CubeArchitecture:
    cube_record = md.cubes.get(cube)
    dim_names = cube_record.dimensions if cube_record else list(md.dimensions)
    nodes: list[DimensionNode] = []
    for name in dim_names:
        drec = md.dimensions.get(name)
        dtype = drec.type if drec else "generic"
        display, group = classify_dimension(dtype, name)
        axis, am = _axis_placement(spec, name)
        members = md.members.get(name, {})
        selected = None
        summary = None
        status = "available"
        if spec is not None:
            if am is not None:
                status = "selected"
                selected = am.selection.member or am.selection.variable
                summary = am.selection.describe()
            else:
                status = "missing"
        nodes.append(DimensionNode(
            name=name, alias=(drec.name if drec else name) if display != "custom" else name,
            type=display, group=group,
            member_count=len(members) or None,
            root_members=_root_members(md, name),
            selected_member=selected, selection_summary=summary,
            used_on_axis=axis, status=status,
        ))
    coverage = form_coverage(md, cube, spec) if spec is not None else None
    return CubeArchitecture(
        application=md.application, cube=cube,
        cube_type=cube_record.type if cube_record else None,
        dimension_count=len(dim_names), dimensions=nodes,
        form_name=spec.name if spec else None, form_coverage=coverage,
    )


def form_coverage(md: TenantMetadata, cube: str, spec: FormSpecification) -> FormCoverage:
    cov = FormCoverage()
    seen: dict[str, int] = {}
    for kind, axis in (("pov", spec.pov), ("pages", spec.pages), ("rows", spec.rows), ("columns", spec.columns)):
        target = getattr(cov, {"pov": "pov", "pages": "pages", "rows": "rows", "columns": "columns"}[kind])
        for am in axis:
            seen[am.dimension] = seen.get(am.dimension, 0) + 1
            target.append({"dimension": am.dimension, "selection": am.selection.describe()})
    cube_record = md.cubes.get(cube)
    cube_dims = cube_record.dimensions if cube_record else list(md.dimensions)
    for dim in cube_dims:
        if dim not in seen:
            cov.missing.append(dim)
    cov.duplicate = [d for d, n in seen.items() if n > 1]
    return cov


def validate_dimension_coverage(md: TenantMetadata, cube: str, spec: FormSpecification) -> DimensionCoverageReport:
    cov = form_coverage(md, cube, spec)
    covered = [d["dimension"] for group in (cov.pov, cov.pages, cov.rows, cov.columns) for d in group]
    invalid: list[str] = []
    for _kind, am in spec.all_axis_members():
        try:
            if not resolve_selection(md, am.dimension, am.selection).members:
                invalid.append(f"{am.dimension}: empty selection")
        except ResolutionError as exc:
            invalid.append(f"{am.dimension}: {exc.message}")
    suggestions = [MissingSuggestion(dimension=d, suggested_handling=_suggest(md, d)) for d in cov.missing]
    warnings = []
    if cov.missing:
        warnings.append(f"{len(cov.missing)} cube dimension(s) will fall back to a default member.")
    return DimensionCoverageReport(
        cube=cube,
        valid=not cov.missing and not cov.duplicate and not invalid,
        covered_dimensions=covered,
        missing_dimensions=cov.missing,
        duplicate_dimensions=cov.duplicate,
        invalid_selections=invalid,
        warnings=warnings,
        suggestions=suggestions,
    )


def _suggest(md: TenantMetadata, dimension: str) -> str:
    # prefer a matching user/subst variable, else a default member, else a root
    for var in md.variables.values():
        if var.dimension == dimension:
            scope = "user variable" if var.scope == "user" else "substitution variable"
            return f"Use the {var.name} {scope}, or place {dimension} on the POV."
    roots = _root_members(md, dimension)
    if roots:
        return f"Add {roots[0]} to the POV or place {dimension} on Pages."
    return f"Place {dimension} on the POV with a fixed member."


def explain_cell_intersection(
    md: TenantMetadata, cube: str, overrides: dict[str, str] | None = None, spec: FormSpecification | None = None
) -> CellIntersection:
    overrides = overrides or {}
    cube_record = md.cubes.get(cube)
    dim_names = cube_record.dimensions if cube_record else list(md.dimensions)
    members: list[CellMember] = []
    for dim in dim_names:
        member, source = _cell_member_for(md, dim, spec, overrides)
        members.append(CellMember(dimension=dim, member=member, source=source))
    expression = "\n× ".join(m.member for m in members)
    return CellIntersection(application=md.application, cube=cube, members=members,
                            expression=expression + "\n\n= One EPM data cell")


def _cell_member_for(md, dim, spec, overrides):  # noqa: ANN001
    if dim in overrides:
        return overrides[dim], "selected"
    axis, am = _axis_placement(spec, dim)
    if am is not None:
        try:
            members = resolve_selection(md, dim, am.selection).members
            if members:
                return members[0], axis
        except ResolutionError:
            pass
        if am.selection.member:
            return am.selection.member, axis
        if am.selection.variable:
            var = md.get_variable(am.selection.variable)
            return (var.value if var and var.value else am.selection.variable), "variable"
    # default: a stored root or a "No <dim>" placeholder
    roots = _root_members(md, dim)
    if roots:
        return roots[0], "default"
    return f"No {dim}", "default"


def compare_cubes(md: TenantMetadata, cube_a: str, cube_b: str) -> CubeComparison:
    a = md.cubes.get(cube_a)
    b = md.cubes.get(cube_b)
    dims_a = set(a.dimensions) if a else set()
    dims_b = set(b.dimensions) if b else set()
    all_dims = sorted(dims_a | dims_b)
    rows = []
    for d in all_dims:
        drec = md.dimensions.get(d)
        detail = (drec.type if drec else None)
        rows.append(CubeComparisonRow(dimension=d, in_a=d in dims_a, in_b=d in dims_b,
                                      detail_a=detail if d in dims_a else None,
                                      detail_b=detail if d in dims_b else None))
    return CubeComparison(
        application=md.application, cube_a=cube_a, cube_b=cube_b, rows=rows,
        shared=len(dims_a & dims_b),
        only_a=sorted(dims_a - dims_b), only_b=sorted(dims_b - dims_a),
    )


def cross_dimensional_size(md: TenantMetadata, cube: str, spec: FormSpecification) -> CrossDimSize:
    areas: list[CrossDimArea] = []

    def area_count(kind: str, axis) -> int:
        total = 1
        details = []
        for am in axis:
            try:
                n = max(1, len(resolve_selection(md, am.dimension, am.selection).members))
            except ResolutionError:
                n = 1
            total *= n
            details.append(f"{n} {am.dimension}")
        if axis:
            areas.append(CrossDimArea(area=kind, detail=" × ".join(details) + f" = {total}", count=total))
        return total

    rows = area_count("rows", spec.rows)
    cols = area_count("columns", spec.columns)
    pages = area_count("pages", spec.pages) if spec.pages else 1
    if spec.pages:
        pass
    total = rows * cols * pages
    size = SizeEstimate(row_combinations=rows, column_combinations=cols, page_combinations=pages, total_cells=total)
    warning = None
    if total > size.warning_threshold:
        warning = f"This design produces about {total:,} potential intersections and may be slow to open."
    return CrossDimSize(cube=cube, areas=areas, total_potential_cells=total, size_estimate=size, warning=warning)


def inspect_dimension_hierarchy(
    md: TenantMetadata, dimension: str, root: str | None = None, cap: int = 50
) -> DimensionHierarchy:
    if root is None:
        roots = _root_members(md, dimension)
        root = roots[0] if roots else dimension
    nodes: list[HierarchyNode] = []
    truncated = False
    stack = [(root, 0)]
    while stack:
        name, depth = stack.pop(0)
        member = md.get_member(dimension, name)
        children = member.children if member else []
        nodes.append(HierarchyNode(name=name, alias=member.alias if member else None,
                                   parent=member.parent if member else None,
                                   depth=depth, has_children=bool(children)))
        if len(nodes) >= cap:
            truncated = len(stack) > 0 or bool(children)
            break
        for child in children:
            stack.append((child, depth + 1))
    # keep outline order: sort by insertion — the BFS above already respects child order
    return DimensionHierarchy(application=md.application, dimension=dimension, root=root,
                              nodes=nodes, truncated=truncated, cap=cap)
