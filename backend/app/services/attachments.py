"""Attachment storage for uploaded spreadsheets (chat file drop).

Files are stored under ``<data_dir>/attachments/<id>/<safe-filename>`` with a
sha256 checksum, a 10 MB size cap and a strict extension allowlist. Every file
is analyzed deterministically at upload time (parse only — no macro execution,
no formula evaluation) and the analysis JSON is persisted next to the file so
later reads don't re-parse.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.base import new_id
from ..db.models import Attachment, Conversation
from ..schemas.api import AttachmentOut
from ..security.redaction import redact_text
from ..spreadsheet import WorkbookAnalysis, analyze_file

ALLOWED_EXTENSIONS = {".xlsx", ".xlsm", ".csv"}
MAX_SIZE_BYTES = 10 * 1024 * 1024
_TEXT_EXTRACT_CAP = 2000
_MEDIA_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".csv": "text/csv",
}
_ANALYSIS_FILENAME = "analysis.json"


class AttachmentError(ValueError):
    """Rejected upload (bad type, too large, unparseable). Maps to HTTP 400."""


def attachments_dir() -> Path:
    return get_settings().data_dir / "attachments"


def safe_filename(raw: str) -> str:
    """Basename-only, conservative character set, no traversal."""
    name = (raw or "").replace("\\", "/").split("/")[-1]
    stem, ext = os.path.splitext(name)
    cleaned = "".join(c if (c.isalnum() or c in " _-.") else "_" for c in stem).strip(" .")
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    return f"{cleaned or 'upload'}{ext.lower()}"


def _analysis_dump(analysis: WorkbookAnalysis) -> str:
    return json.dumps(analysis.model_dump(by_alias=True, mode="json"), indent=2, sort_keys=True) + "\n"


def _text_extract(filename: str, analysis: WorkbookAnalysis) -> str:
    lines = [filename]
    for sheet in analysis.sheets:
        headers = ", ".join(c.header for c in sheet.columns if c.header)
        lines.append(f"sheet {sheet.name} [{sheet.kind}] headers: {headers}".rstrip(": "))
    return redact_text("\n".join(lines))[:_TEXT_EXTRACT_CAP]


def save_attachment(
    session: Session,
    conversation: Conversation,
    filename: str,
    data: bytes,
) -> tuple[Attachment, WorkbookAnalysis]:
    name = safe_filename(filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise AttachmentError(f"unsupported file type '{ext or name}': allowed extensions are {allowed}")
    if not data:
        raise AttachmentError("uploaded file is empty")
    if len(data) > MAX_SIZE_BYTES:
        raise AttachmentError(
            f"file is {len(data)} bytes; the limit is {MAX_SIZE_BYTES} bytes (10 MB)"
        )

    attachment_id = new_id()
    directory = attachments_dir() / attachment_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    try:
        analysis = analyze_file(path, name)
    except Exception as exc:
        shutil.rmtree(directory, ignore_errors=True)
        raise AttachmentError(f"could not parse {name}: {redact_text(str(exc))}") from exc
    (directory / _ANALYSIS_FILENAME).write_text(_analysis_dump(analysis), encoding="utf-8")

    attachment = Attachment(
        id=attachment_id,
        project_id=conversation.project_id,
        conversation_id=conversation.id,
        filename=name,
        media_type=_MEDIA_TYPES[ext],
        size_bytes=len(data),
        path=str(path),
        checksum=hashlib.sha256(data).hexdigest(),
        text_extract=_text_extract(name, analysis),
    )
    session.add(attachment)
    session.flush()
    return attachment, analysis


def get_attachment(session: Session, attachment_id: str) -> Attachment | None:
    return session.get(Attachment, attachment_id)


def load_analysis(attachment: Attachment) -> WorkbookAnalysis:
    """Load the stored analysis; re-parse deterministically if it is missing."""
    stored = Path(attachment.path).parent / _ANALYSIS_FILENAME
    if stored.exists():
        return WorkbookAnalysis.model_validate_json(stored.read_text(encoding="utf-8"))
    return analyze_file(Path(attachment.path), attachment.filename)


def to_out(attachment: Attachment, analysis: WorkbookAnalysis) -> AttachmentOut:
    return AttachmentOut(
        id=attachment.id,
        conversation_id=attachment.conversation_id,
        project_id=attachment.project_id,
        filename=attachment.filename,
        media_type=attachment.media_type,
        size_bytes=attachment.size_bytes,
        checksum=attachment.checksum,
        sheet_names=[s.name for s in analysis.sheets],
        kind_guess=analysis.kind_guess,
    )
