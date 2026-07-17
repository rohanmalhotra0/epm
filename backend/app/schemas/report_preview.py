"""Deterministic report preview model (mirrors form_preview for reports).

Unlike a form (which shows "—" placeholders), a report preview carries sampled
*numeric* values so the rendered artifact looks like a real report in Demo Mode.
Values are deterministic (derived from a stable hash of the intersection) so the
same spec always renders identically.
"""

from __future__ import annotations

from pydantic import Field

from .common import CamelModel
from .validation import SizeEstimate


class ReportCell(CamelModel):
    value: float | None = None
    formatted: str = "—"
    color: str | None = None
    background: str | None = None
    bold: bool = False
    negative: bool = False
    note: str | None = None


class ReportRowPreview(CamelModel):
    label: str
    cells: list[ReportCell] = Field(default_factory=list)
    total: ReportCell | None = None


class ReportGridPreview(CamelModel):
    name: str
    pov: list[str] = Field(default_factory=list)
    pages: list[str] = Field(default_factory=list)
    column_labels: list[str] = Field(default_factory=list)
    rows: list[ReportRowPreview] = Field(default_factory=list)
    column_totals: list[ReportCell] = Field(default_factory=list)
    show_row_totals: bool = False
    show_column_totals: bool = True
    rows_truncated: bool = False
    columns_truncated: bool = False
    chart_type: str = "none"
    chart_title: str | None = None
    size_estimate: SizeEstimate | None = None


class ReportPreview(CamelModel):
    report_name: str
    application: str
    cube: str
    folder: str
    report_type: str = "grid"
    validation_status: str = "valid"
    use_aliases: bool = True
    rule_associations: list[str] = Field(default_factory=list)
    grids: list[ReportGridPreview] = Field(default_factory=list)
