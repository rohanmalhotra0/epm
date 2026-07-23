"""Standalone workbook inspection.

``POST /api/spreadsheet/inspect`` takes an uploaded Excel workbook and returns a
full :class:`WorkbookInspection` — every macro's source, plus named ranges,
tables, pivots, charts, data connections and the auto-run hooks. Unlike the
attachments flow it is **stateless**: no conversation, no project, nothing
written to the database. Owner-scoped (the caller must be signed in), so the
Chrome extension can call it with its session cookie.

Parse only — no macro execution, no formula evaluation, ever.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..security.redaction import redact_text
from ..spreadsheet import WorkbookInspection, inspect_file
from .deps import get_current_owner

router = APIRouter(tags=["spreadsheet"])

# Macro-heavy workbooks with embedded pivots/queries run larger than a plain
# data drop, so allow more headroom than the 10 MB attachment cap.
INSPECT_MAX_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm", ".xlsb", ".csv"}


async def run_inspection(file: UploadFile) -> WorkbookInspection:
    """Parse an uploaded workbook (no owner scoping — the caller's route decides
    how to authenticate). Shared by the session-gated and token-gated routes."""
    filename = Path(file.filename or "workbook.xlsx").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(400, f"unsupported file type '{ext or filename}'; allowed: {allowed}")

    from .routes_context import _read_limited
    data = await _read_limited(file, INSPECT_MAX_BYTES)
    if not data:
        raise HTTPException(400, "empty file")

    # Write to a temp file with the right suffix (openpyxl/oletools open by path).
    with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            return inspect_file(
                Path(tmp.name),
                filename=redact_text(filename)[:255],
                size_bytes=len(data),
            )
        except Exception as exc:  # noqa: BLE001 — never leak a stack trace to the client
            raise HTTPException(422, f"could not inspect workbook: {str(exc)[:200]}") from exc


@router.post("/api/spreadsheet/inspect", response_model=WorkbookInspection)
async def inspect_workbook(
    file: UploadFile = File(...),
    _owner: str = Depends(get_current_owner),
) -> WorkbookInspection:
    return await run_inspection(file)
