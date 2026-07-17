"""Canonical ReportSpecification (agent-generated report artifact).

A report is a *read* artifact: unlike a data-entry form it presents computed /
sampled values in one or more grids, optionally with a chart, and carries
Oracle-EPM-style "smart formatting" (number scaling, decimals, negative styling,
currency/percent affixes and conditional colour rules).

The language model *proposes* this structure; Pydantic validates it; the same
tenant metadata + deterministic renderers that back forms consume it. The model
never owns the deployable artifact.

Axis placement (``pov``/``pages``/``rows``/``columns``) deliberately reuses the
form ``AxisMember`` model so the existing resolver / preview engine works
unchanged for reports too.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .common import CamelModel
from .form_spec import AxisMember, BusinessRuleAssociation, DisplayOptions, GenerationMetadata

REPORT_SPEC_SCHEMA_VERSION = "1.0.0"


class ReportType(str, Enum):
    grid = "grid"
    dashboard = "dashboard"
    financial = "financial"


class ChartType(str, Enum):
    none = "none"
    bar = "bar"
    line = "line"
    area = "area"
    pie = "pie"


class NegativeStyle(str, Enum):
    """How negative numbers render (Oracle Smart Formatting)."""

    minus = "minus"  # -1,234
    parentheses = "parentheses"  # (1,234)
    red = "red"  # red -1,234
    red_parentheses = "redParentheses"  # red (1,234)


class Comparator(str, Enum):
    lt = "lt"
    le = "le"
    gt = "gt"
    ge = "ge"
    eq = "eq"
    ne = "ne"


class ConditionalRule(CamelModel):
    """A conditional-formatting rule applied to a cell's numeric value."""

    comparator: Comparator = Comparator.gt
    value: float = 0.0
    color: str | None = Field(None, description="Hex text colour, e.g. #da1e28")
    background: str | None = Field(None, description="Hex cell background")
    bold: bool = False
    label: str | None = None


class SmartFormat(CamelModel):
    """Oracle-EPM-style number formatting for a grid, column or single cell."""

    decimal_places: int = Field(0, ge=0, le=10)
    thousands_separator: bool = True
    scale: int = Field(0, description="Divide display value by 10**scale (0=none, 3=K, 6=M)")
    negative_style: NegativeStyle = NegativeStyle.minus
    prefix: str = Field("", description="Leading symbol, e.g. $")
    suffix: str = Field("", description="Trailing symbol, e.g. %")
    conditional_rules: list[ConditionalRule] = Field(default_factory=list)


class CellOverride(CamelModel):
    """A per-cell edit produced by an inline prompt in the artifact panel."""

    value: float | None = Field(None, description="Override the sampled value")
    format: SmartFormat | None = Field(None, description="Per-cell formatting override")
    note: str | None = Field(None, description="Analyst annotation shown on hover")


class ReportChart(CamelModel):
    type: ChartType = ChartType.none
    title: str | None = None
    series_from: str = Field("columns", description="'columns' or 'rows' — which axis becomes series")
    stacked: bool = False


class ReportGrid(CamelModel):
    """One grid within a report. Reuses the form axis model for resolution."""

    name: str = Field("Grid", min_length=1, max_length=80)
    pov: list[AxisMember] = Field(default_factory=list)
    pages: list[AxisMember] = Field(default_factory=list)
    rows: list[AxisMember] = Field(default_factory=list)
    columns: list[AxisMember] = Field(default_factory=list)

    smart_format: SmartFormat = Field(default_factory=SmartFormat)
    # Per-column formatting overrides, keyed by the column's resolved label.
    column_formats: dict[str, SmartFormat] = Field(default_factory=dict)
    # Per-cell overrides keyed by "rowLabel||columnLabel".
    cell_overrides: dict[str, CellOverride] = Field(default_factory=dict)

    show_row_totals: bool = False
    show_column_totals: bool = True
    chart: ReportChart | None = None

    @model_validator(mode="after")
    def _structural(self) -> ReportGrid:
        if not self.rows:
            raise ValueError("report grid must have at least one row dimension")
        if not self.columns:
            raise ValueError("report grid must have at least one column dimension")
        return self


class ReportSpecification(CamelModel):
    schema_version: str = REPORT_SPEC_SCHEMA_VERSION
    report_type: ReportType = ReportType.grid
    name: str = Field(..., min_length=1, max_length=80)
    description: str | None = None
    application: str
    cube: str
    folder: str = "EPM Wizard/Reports"

    grids: list[ReportGrid] = Field(default_factory=list)
    display: DisplayOptions = Field(default_factory=DisplayOptions)
    business_rule_associations: list[BusinessRuleAssociation] = Field(default_factory=list)

    context_version: str | None = None
    generation: GenerationMetadata | None = None

    @model_validator(mode="after")
    def _structural(self) -> ReportSpecification:
        if not self.grids:
            raise ValueError("report must have at least one grid")
        return self

    def dimensions_used(self) -> list[str]:
        out: list[str] = []
        for grid in self.grids:
            for axis in (grid.pov, grid.pages, grid.rows, grid.columns):
                out.extend(am.dimension for am in axis)
        return out
