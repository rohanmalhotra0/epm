"""Spreadsheet attachment routes: upload into a conversation, read back the
stored metadata and the full deterministic workbook analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..schemas.api import AttachmentOut
from ..services import attachments as attachments_svc
from ..services import conversations as conversations_svc
from ..spreadsheet import WorkbookAnalysis
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
    data = await file.read()
    try:
        attachment, analysis = attachments_svc.save_attachment(
            session, conversation, file.filename or "upload", data
        )
    except attachments_svc.AttachmentError as exc:
        raise HTTPException(400, str(exc)) from exc
    return attachments_svc.to_out(attachment, analysis)


@router.get("/api/attachments/{attachment_id}", response_model=AttachmentOut)
def get_attachment(attachment_id: str, session: Session = Depends(get_db)) -> AttachmentOut:
    attachment = attachments_svc.get_attachment(session, attachment_id)
    if attachment is None:
        raise HTTPException(404, "attachment not found")
    return attachments_svc.to_out(attachment, attachments_svc.load_analysis(attachment))


@router.get("/api/attachments/{attachment_id}/analysis", response_model=WorkbookAnalysis)
def get_attachment_analysis(attachment_id: str, session: Session = Depends(get_db)) -> WorkbookAnalysis:
    attachment = attachments_svc.get_attachment(session, attachment_id)
    if attachment is None:
        raise HTTPException(404, "attachment not found")
    return attachments_svc.load_analysis(attachment)
