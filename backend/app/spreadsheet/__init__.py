"""Deterministic spreadsheet ingestion (chat file drop).

Uploaded workbooks are ONLY ever parsed — no macro execution, no formula
evaluation, ever. VBA code is extracted as inert text (oletools) and redacted;
formulas are recorded as strings.
"""

from __future__ import annotations

from .models import SheetAnalysis, SheetKind, WorkbookAnalysis
from .parser import analyze_file

__all__ = ["SheetAnalysis", "SheetKind", "WorkbookAnalysis", "analyze_file"]
