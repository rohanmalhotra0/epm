"""Conversation + streaming chat routes (spec sections 7, 8)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..agent import stream_turn
from ..db.base import get_sessionmaker
from ..db.models import Attachment
from ..schemas.api import ConversationCreate, ConversationOut, ConversationUpdate
from ..schemas.chat import ChatMessageIn, MessageOut, StreamEvent, StreamEventType
from ..db.models import Project
from ..security.redaction import looks_like_secret, redact_text
from ..services import conversations as svc
from .deps import authorize_project_id, get_current_owner, get_db, require_project, resolve_turn

router = APIRouter(tags=["conversations"])


def _authorize_conversation(conversation_id: str, owner: str) -> None:
    """Ownership guard for the streaming routes, which persist via their own
    sessionmaker and must run the check (in its own short-lived session, closed
    before any SSE body starts) before streaming begins. Raises 404 both when
    the conversation is missing and when the owner may not access its project."""
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        conv = svc.get_conversation(session, conversation_id)
        if conv is None:
            raise HTTPException(404, "conversation not found")
        authorize_project_id(session, owner, conv.project_id)
    finally:
        session.close()


@router.get("/api/projects/{project_id}/conversations", response_model=list[ConversationOut])
def list_conversations(search: str | None = None, include_archived: bool = False,
                       project: Project = Depends(require_project),
                       session: Session = Depends(get_db)) -> list[ConversationOut]:
    return svc.list_conversations(session, project.id, search=search, include_archived=include_archived)


@router.post("/api/projects/{project_id}/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(body: ConversationCreate, project: Project = Depends(require_project),
                        session: Session = Depends(get_db)) -> ConversationOut:
    conv = svc.create_conversation(session, project.id, body.title)
    return svc._conv_out(session, conv)


@router.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(conversation_id: str, session: Session = Depends(get_db),
                 owner: str = Depends(get_current_owner)) -> list[MessageOut]:
    conv = svc.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    authorize_project_id(session, owner, conv.project_id)
    return [svc.message_out(m) for m in svc.get_active_messages(session, conversation_id)]


@router.patch("/api/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(conversation_id: str, body: ConversationUpdate, session: Session = Depends(get_db),
                        owner: str = Depends(get_current_owner)) -> ConversationOut:
    conv = svc.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    authorize_project_id(session, owner, conv.project_id)
    conv = svc.update_conversation(session, conversation_id, **body.model_dump(exclude_none=True))
    if conv is None:
        raise HTTPException(404, "conversation not found")
    return svc._conv_out(session, conv)


@router.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, session: Session = Depends(get_db),
                        owner: str = Depends(get_current_owner)) -> None:
    conv = svc.get_conversation(session, conversation_id)
    if conv is not None:
        authorize_project_id(session, owner, conv.project_id)
    svc.delete_conversation(session, conversation_id)


def _persist_user_message(
    conversation_id: str, content: str, attachment_ids: list[str] | None = None
) -> tuple[str, str, list[str]]:
    """Persist the (redacted) user message in its own committed transaction and
    link any uploaded attachments to it. Unknown attachment ids are ignored."""
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        conv = svc.get_conversation(session, conversation_id)
        if conv is None:
            raise HTTPException(404, "conversation not found")
        safe = redact_text(content) if looks_like_secret(content) else content
        msg = svc.add_message(session, conversation_id, role="user", content=safe)
        linked: list[str] = []
        for attachment_id in attachment_ids or []:
            attachment = session.get(Attachment, attachment_id)
            # Confused-deputy guard: only link attachments belonging to THIS
            # conversation's project. Otherwise a caller could reference another
            # owner's attachment id and have its (parsed) contents pulled into
            # their own turn — cross-owner data exfiltration.
            if attachment is None or attachment.project_id != conv.project_id:
                continue
            attachment.message_id = msg.id
            if not attachment.conversation_id:
                attachment.conversation_id = conversation_id
            linked.append(attachment.id)
        session.commit()
        return msg.id, safe, linked
    finally:
        session.close()


async def _sse(conversation_id: str, user_text: str, attachment_ids: list[str] | None = None) -> AsyncIterator[str]:
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        conv = svc.get_conversation(session, conversation_id)
        if conv is None:
            yield StreamEvent(type=StreamEventType.error, data={"message": "conversation not found"}).sse()
            yield StreamEvent(type=StreamEventType.done, data={}).sse()
            return
        project = conv.project
        turn = resolve_turn(session, project, conv)
        # An AI turn can stream for many seconds. Commit the turn-resolution reads now
        # so no DB transaction (or WAL read snapshot) is held open across the stream —
        # the assistant message is persisted in its own short transaction below. The
        # sessionmaker uses expire_on_commit=False, so conv/project/turn stay usable.
        session.commit()
        yield StreamEvent(type=StreamEventType.title, data={"title": conv.title}).sse()
        async for event in stream_turn(
            session=session, project=project, conversation=conv,
            connector=turn.connector, provider=turn.provider, application=turn.application,
            classification=turn.classification, environment_name=turn.environment_name,
            demo=turn.demo, context_version_id=turn.context_version_id, user_text=user_text,
            attachment_ids=attachment_ids,
        ):
            yield event.sse()
        session.commit()
    except Exception as exc:  # ensure the client always gets a terminal event
        session.rollback()
        yield StreamEvent(type=StreamEventType.error, data={"message": str(exc)[:300]}).sse()
        yield StreamEvent(type=StreamEventType.done, data={}).sse()
    finally:
        session.close()


def _stream_response(
    conversation_id: str, user_text: str, attachment_ids: list[str] | None = None
) -> StreamingResponse:
    return StreamingResponse(
        _sse(conversation_id, user_text, attachment_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/api/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, body: ChatMessageIn,
                 owner: str = Depends(get_current_owner)) -> StreamingResponse:
    # Ownership is enforced BEFORE any persistence or streaming begins.
    _authorize_conversation(conversation_id, owner)
    _msg_id, safe, linked = _persist_user_message(conversation_id, body.content, body.attachments)
    return _stream_response(conversation_id, safe, linked)


@router.post("/api/conversations/{conversation_id}/messages/{message_id}/branch")
def branch_message(conversation_id: str, message_id: str, body: ChatMessageIn,
                   owner: str = Depends(get_current_owner)) -> StreamingResponse:
    # Ownership is enforced BEFORE any persistence or streaming begins.
    _authorize_conversation(conversation_id, owner)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        # Confused-deputy guard: the message must belong to the (already
        # authorized) conversation. branch_from_user_edit resolves the message
        # purely by id and mutates target.conversation_id's history, so without
        # this an owner could branch/deactivate another owner's messages and
        # inject into their conversation by pairing their own conversation_id
        # with a foreign message_id.
        from ..db.models import Message
        target = session.get(Message, message_id)
        if target is None or target.conversation_id != conversation_id:
            raise HTTPException(404, "message not found")
        new_msg = svc.branch_from_user_edit(session, message_id, body.content)
        if new_msg is None:
            raise HTTPException(400, "cannot branch from this message")
        session.commit()
        text = new_msg.content
    finally:
        session.close()
    return _stream_response(conversation_id, text)
