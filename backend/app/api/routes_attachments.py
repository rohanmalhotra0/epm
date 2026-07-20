"""Attachment routes (spreadsheets and LCM snapshot zips): upload into a
conversation, read back the stored metadata and the full deterministic
analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..schemas.api import AttachmentOut
from ..services import attachments as attachments_svc
from ..services import conversations as conversations_svc
from .deps import get_db

router = APIRouter(tags=["attachments"])


@router.post(
    "/api/conversations/{conversation_id}/attachments",
    response_model=AttachmentOut,
    status_code=201,
)
async def upload_attachment(
    conversation_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> AttachmentOut:
    conversation = conversations_svc.get_conversation(session, conversation_id)
    if conversation is None:
        raise HTTPException(404, "conversation not found")
    from .routes_context import _read_limited
    data = await _read_limited(file)
    try:
        attachment, analysis = attachments_svc.save_attachment(
            session, conversation, file.filename or "upload", data
        )
    except attachments_svc.AttachmentError as exc:
        raise HTTPException(400, str(exc)) from exc
    return attachments_svc.to_out(attachment, analysis)


def _load_analysis(attachment):
    if attachment.media_type == attachments_svc.ZIP_MEDIA_TYPE:
        return attachments_svc.load_snapshot_analysis(attachment)
    return attachments_svc.load_analysis(attachment)


@router.get("/api/attachments/{attachment_id}", response_model=AttachmentOut)
def get_attachment(attachment_id: str, session: Session = Depends(get_db)) -> AttachmentOut:
    attachment = attachments_svc.get_attachment(session, attachment_id)
    if attachment is None:
        raise HTTPException(404, "attachment not found")
    return attachments_svc.to_out(attachment, _load_analysis(attachment))


@router.get("/api/attachments/{attachment_id}/analysis")
def get_attachment_analysis(attachment_id: str, session: Session = Depends(get_db)) -> dict:
    """The stored deterministic analysis: a ``WorkbookAnalysis`` for
    spreadsheets, a ``SnapshotAnalysis`` for LCM snapshot zips (the payload is
    a plain JSON object because the shape depends on the attachment type)."""
    attachment = attachments_svc.get_attachment(session, attachment_id)
    if attachment is None:
        raise HTTPException(404, "attachment not found")
    return _load_analysis(attachment).model_dump(by_alias=True, mode="json")
