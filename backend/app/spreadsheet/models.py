"""DTOs for the deterministic spreadsheet analysis engine.

CamelModel (camelCase JSON) like the rest of the API surface, but deliberately
NOT registered in ``CANONICAL_MODELS`` — these are backend analysis structures
consumed by the attachments API and the (separate) chat skill, not canonical
artifact schemas.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from ..schemas.common import CamelModel


class ColumnRole(str, Enum):
    member = "member"
    parent = "parent"
    alias = "alias"
    level = "level"
    data = "data"
    period = "period"
    label = "label"
    unknown = "unknown"


class SheetKind(str, Enum):
    chart_of_accounts = "chartOfAccounts"
    layout = "layout"
    data_table = "dataTable"
    unknown = "unknown"


class ColumnInfo(CamelModel):
    index: int
    header: str = ""
    role: ColumnRole = ColumnRole.unknown


class ParsedMember(CamelModel):
    name: str
    parent: str | None = None
    alias: str | None = None
    storage: str | None = None


class HierarchyParse(CamelModel):
    dimension_guess: str
    members: list[ParsedMember] = Field(default_factory=list)
    root_count: int = 0
    issues: list[str] = Field(default_factory=list)


class LayoutParse(CamelModel):
    row_labels: list[str] = Field(default_factory=list)
    column_labels: list[str] = Field(default_factory=list)
    pov_hints: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class DataTableParse(CamelModel):
    period_columns: list[str] = Field(default_factory=list)
    label_column: str | None = None
    row_count: int = 0
    sample_rows: list[list[str]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class FormulaInfo(CamelModel):
    sheet: str
    cell: str
    formula: str


class VbaModule(CamelModel):
    name: str
    line_count: int = 0
    code: str = ""


class SheetAnalysis(CamelModel):
    name: str
    kind: SheetKind = SheetKind.unknown
    columns: list[ColumnInfo] = Field(default_factory=list)
    hierarchy: HierarchyParse | None = None
    layout: LayoutParse | None = None
    data_table: DataTableParse | None = None
    formulas: list[FormulaInfo] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class WorkbookAnalysis(CamelModel):
    filename: str
    sheets: list[SheetAnalysis] = Field(default_factory=list)
    vba_modules: list[VbaModule] = Field(default_factory=list)
    kind_guess: SheetKind = SheetKind.unknown
