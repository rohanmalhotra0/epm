"""Deterministic report preview generation (report analogue of preview.py)."""

from __future__ import annotations

from ..schemas.report_preview import (
    ReportCell,
    ReportGridPreview,
    ReportPreview,
    ReportRowPreview,
)
from ..schemas.report_spec import ChartType, ReportGrid, ReportSpecification, SmartFormat
from ..schemas.validation import SizeEstimate
from .formatting import build_cell, merge_format, sample_value
from .metadata import TenantMetadata
from .resolver import ResolutionError, resolve_selection

GRID_ROWS = 20
GRID_COLS = 16


def _labels(md: TenantMetadata, dimension, selection, use_aliases: bool) -> tuple[list[str], bool]:
    try:
        members = resolve_selection(md, dimension, selection).members
    except ResolutionError:
        return ["(unresolved)"], True
    labels = [
        (md.alias_of(dimension, n) or n) if use_aliases else n for n in members
    ]
    return labels, False


def _axis_labels(md: TenantMetadata, axis, use_aliases: bool) -> tuple[list[str], bool]:
    """Cross-join every dimension on an axis into combined labels."""
    label_sets: list[list[str]] = []
    err = False
    for am in axis:
        labels, e = _labels(md, am.dimension, am.selection, use_aliases)
        label_sets.append(labels)
        err = err or e
    if not label_sets:
        return [], err
    from itertools import product

    combined = [" · ".join(combo) for combo in product(*label_sets)]
    return combined, err


def _point_label(md: TenantMetadata, axis, use_aliases: bool) -> list[str]:
    out: list[str] = []
    for am in axis:
        labels, _ = _labels(md, am.dimension, am.selection, use_aliases)
        head = labels[0] if labels else am.selection.describe()
        out.append(f"{am.dimension}: {head}")
    return out


def _grid_format(grid: ReportGrid, column_label: str) -> SmartFormat:
    return merge_format(grid.smart_format, grid.column_formats.get(column_label))


def build_grid_preview(spec: ReportSpecification, grid: ReportGrid, md: TenantMetadata) -> tuple[ReportGridPreview, bool]:
    use_aliases = spec.display.use_aliases
    col_labels, col_err = _axis_labels(md, grid.columns, use_aliases)
    row_labels, row_err = _axis_labels(md, grid.rows, use_aliases)

    cols_trunc = len(col_labels) > GRID_COLS
    rows_trunc = len(row_labels) > GRID_ROWS
    col_labels_v = col_labels[:GRID_COLS]
    row_labels_v = row_labels[:GRID_ROWS]

    col_totals_raw = [0.0] * len(col_labels_v)
    rows: list[ReportRowPreview] = []
    for rlabel in row_labels_v:
        cells: list[ReportCell] = []
        row_total_raw = 0.0
        for ci, clabel in enumerate(col_labels_v):
            fmt = _grid_format(grid, clabel)
            override = grid.cell_overrides.get(f"{rlabel}||{clabel}")
            if override and override.value is not None:
                raw = override.value
            else:
                raw = sample_value(spec.cube, grid.name, rlabel, clabel)
            cell_fmt = merge_format(fmt, override.format if override else None)
            note = override.note if override else None
            cell = build_cell(raw, cell_fmt, note=note)
            cells.append(cell)
            row_total_raw += raw
            col_totals_raw[ci] += raw
        total_cell = None
        if grid.show_row_totals:
            total_cell = build_cell(row_total_raw, grid.smart_format)
        rows.append(ReportRowPreview(label=rlabel, cells=cells, total=total_cell))

    col_totals: list[ReportCell] = []
    if grid.show_column_totals:
        col_totals = [build_cell(t, grid.smart_format) for t in col_totals_raw]

    size = SizeEstimate(
        row_combinations=len(row_labels),
        column_combinations=len(col_labels),
        page_combinations=1,
        total_cells=len(row_labels) * len(col_labels),
    )
    chart = grid.chart
    preview = ReportGridPreview(
        name=grid.name,
        pov=_point_label(md, grid.pov, use_aliases),
        pages=_point_label(md, grid.pages, use_aliases),
        column_labels=col_labels_v,
        rows=rows,
        column_totals=col_totals,
        show_row_totals=grid.show_row_totals,
        show_column_totals=grid.show_column_totals,
        rows_truncated=rows_trunc,
        columns_truncated=cols_trunc,
        chart_type=(chart.type.value if isinstance(chart.type, ChartType) else str(chart.type)) if chart else "none",
        chart_title=chart.title if chart else None,
        size_estimate=size,
    )
    return preview, (col_err or row_err)


def build_report_preview(spec: ReportSpecification, md: TenantMetadata) -> ReportPreview:
    grids: list[ReportGridPreview] = []
    any_error = False
    for grid in spec.grids:
        gp, err = build_grid_preview(spec, grid, md)
        grids.append(gp)
        any_error = any_error or err
    return ReportPreview(
        report_name=spec.name,
        application=spec.application,
        cube=spec.cube,
        folder=spec.folder,
        report_type=spec.report_type.value if hasattr(spec.report_type, "value") else str(spec.report_type),
        validation_status="invalid" if any_error else "valid",
        use_aliases=spec.display.use_aliases,
        rule_associations=[a.rule_name for a in spec.business_rule_associations],
        grids=grids,
    )
