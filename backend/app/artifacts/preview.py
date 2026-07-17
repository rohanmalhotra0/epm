"""Deterministic form preview generation (spec section 24)."""

from __future__ import annotations

from itertools import product

from ..schemas.form_preview import FormPreview, PreviewAxis, ResolvedMember
from ..schemas.form_spec import AxisMember, FormSpecification
from ..schemas.validation import SizeEstimate
from .metadata import TenantMetadata
from .resolver import ResolutionError, resolve_selection

SAMPLE = 10
GRID_ROWS = 15
GRID_COLS = 15


def _axis_preview(md: TenantMetadata, kind: str, am: AxisMember, use_aliases: bool) -> tuple[PreviewAxis, list[str], bool]:
    try:
        res = resolve_selection(md, am.dimension, am.selection)
        members = res.members
        error = False
    except ResolutionError:
        members = []
        error = True
    samples = []
    for name in members[:SAMPLE]:
        alias = md.alias_of(am.dimension, name)
        samples.append(ResolvedMember(name=name, alias=alias))
    labels = [
        (md.alias_of(am.dimension, n) or n) if use_aliases else n for n in members
    ]
    axis = PreviewAxis(
        kind=kind,
        dimension=am.dimension,
        selection_summary=am.selection.describe(),
        resolved_count=len(members),
        sample_members=samples,
        suppress_missing=am.suppress_missing,
        truncated=len(members) > SAMPLE,
    )
    return axis, labels, error


def build_preview(spec: FormSpecification, md: TenantMetadata) -> FormPreview:
    use_aliases = spec.display.use_aliases

    pov_axes, page_axes, row_axes, col_axes = [], [], [], []
    row_label_sets: list[list[str]] = []
    col_label_sets: list[list[str]] = []
    page_counts: list[int] = []
    any_error = False

    for am in spec.pov:
        ax, _labels, err = _axis_preview(md, "pov", am, use_aliases)
        pov_axes.append(ax)
        any_error = any_error or err
    for am in spec.pages:
        ax, _labels, err = _axis_preview(md, "page", am, use_aliases)
        page_axes.append(ax)
        page_counts.append(max(1, ax.resolved_count))
        any_error = any_error or err
    for am in spec.rows:
        ax, labels, err = _axis_preview(md, "row", am, use_aliases)
        row_axes.append(ax)
        row_label_sets.append(labels or ["(unresolved)"])
        any_error = any_error or err
    for am in spec.columns:
        ax, labels, err = _axis_preview(md, "column", am, use_aliases)
        col_axes.append(ax)
        col_label_sets.append(labels or ["(unresolved)"])
        any_error = any_error or err

    row_combos = _product([len(s) for s in row_label_sets]) if row_label_sets else 0
    col_combos = _product([len(s) for s in col_label_sets]) if col_label_sets else 0
    page_combos = _product(page_counts) if page_counts else 1
    size = SizeEstimate(
        row_combinations=row_combos,
        column_combinations=col_combos,
        page_combinations=page_combos,
        total_cells=row_combos * col_combos * page_combos,
    )

    row_labels, rows_trunc = _cross_labels(row_label_sets, GRID_ROWS)
    col_labels, cols_trunc = _cross_labels(col_label_sets, GRID_COLS)

    return FormPreview(
        form_name=spec.name,
        application=spec.application,
        cube=spec.cube,
        folder=spec.folder,
        validation_status="invalid" if any_error else "valid",
        reference_template=spec.reference_template.name if spec.reference_template else None,
        use_aliases=use_aliases,
        hidden_members=spec.display.hidden_members,
        rule_associations=[a.rule_name for a in spec.business_rule_associations],
        pov=pov_axes,
        pages=page_axes,
        rows=row_axes,
        columns=col_axes,
        row_labels=row_labels,
        column_labels=col_labels,
        rows_truncated=rows_trunc,
        columns_truncated=cols_trunc,
        size_estimate=size,
    )


def _product(nums: list[int]) -> int:
    total = 1
    for n in nums:
        total *= max(0, n)
    return total


def _cross_labels(label_sets: list[list[str]], cap: int) -> tuple[list[str], bool]:
    if not label_sets:
        return [], False
    combined = [" · ".join(combo) for combo in product(*label_sets)]
    if len(combined) > cap:
        return combined[:cap], True
    return combined, False
