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
    # The label-column values. Carried so a data table can feed the form/report
    # builder, which previously only worked for `layout` sheets.
    row_labels: list[str] = Field(default_factory=list)
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


# --- workbook inspection (the "see everything" surface) ---------------------
# A richer, structural view than WorkbookAnalysis: every macro's source PLUS the
# other moving parts — named ranges, tables, pivots, charts, data connections —
# and the auto-run hooks that make a workbook "go". Parse-only, like everything
# else here: nothing is compiled, evaluated or executed.


class SheetSummary(CamelModel):
    name: str
    index: int
    # visible | hidden | veryHidden — "very hidden" sheets are only reachable
    # from the VBA editor, so they matter when auditing a workbook.
    visibility: str = "visible"
    dimensions: str = ""          # e.g. "A1:H50"
    rows: int = 0
    cols: int = 0
    formula_count: int = 0
    table_count: int = 0
    chart_count: int = 0
    pivot_count: int = 0
    kind: SheetKind = SheetKind.unknown


class NamedRange(CamelModel):
    name: str
    refers_to: str = ""
    # "workbook" for a global name, else the owning sheet name.
    scope: str = "workbook"
    hidden: bool = False


class TableInfo(CamelModel):
    name: str
    sheet: str = ""
    ref: str = ""                 # e.g. "A1:F200"
    columns: list[str] = Field(default_factory=list)


class PivotTableInfo(CamelModel):
    name: str
    sheet: str = ""
    location: str = ""            # anchor ref of the pivot on its sheet
    source: str = ""              # cache source (worksheet range or connection)


class ChartInfo(CamelModel):
    sheet: str = ""
    chart_type: str = ""          # e.g. "BarChart", "LineChart"
    title: str = ""


class DataConnection(CamelModel):
    name: str = ""
    type: str = ""                # e.g. "OLE DB", "Web", "Worksheet", "Text"
    source: str = ""              # server/db/url/path (redacted)
    command: str = ""             # query/command text (redacted)


class VbaProcedure(CamelModel):
    module: str
    name: str
    kind: str = "Sub"            # Sub | Function | Property Get/Let/Set
    signature: str = ""          # the declaration line, redacted
    # True when this proc runs itself on an Excel/Workbook/Worksheet event
    # (Workbook_Open, Auto_Open, Worksheet_Change, …) rather than being called.
    auto_run: bool = False


class WorkbookTrigger(CamelModel):
    """A hook that makes the workbook act on its own."""

    name: str                     # e.g. "Workbook_Open", "Auto_Open"
    module: str = ""
    scope: str = "event"          # "auto" (Auto_*) | "event" (host event handler)


class WorkbookInspection(CamelModel):
    filename: str
    size_bytes: int = 0
    file_format: str = ""         # xlsx | xlsm | xlsb | csv
    macro_enabled: bool = False
    has_macros: bool = False
    summary: str = ""             # one-line human overview
    sheet_count: int = 0
    sheets: list[SheetSummary] = Field(default_factory=list)
    vba_modules: list[VbaModule] = Field(default_factory=list)
    procedures: list[VbaProcedure] = Field(default_factory=list)
    triggers: list[WorkbookTrigger] = Field(default_factory=list)
    named_ranges: list[NamedRange] = Field(default_factory=list)
    tables: list[TableInfo] = Field(default_factory=list)
    pivot_tables: list[PivotTableInfo] = Field(default_factory=list)
    charts: list[ChartInfo] = Field(default_factory=list)
    connections: list[DataConnection] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    # Prompt-ready, redacted workbook reference used by the browser agent.
    # This is deliberately bounded by the inspector so it is safe to keep in
    # chrome.storage.session and send with each agent step.
    ai_context: str = ""
    ai_context_truncated: bool = False
