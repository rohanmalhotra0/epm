"""Conversation + message persistence, including edit/branch (spec section 7)."""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db.base import utcnow
from ..db.models import Conversation, Message
from ..schemas.api import ConversationOut
from ..schemas.chat import ChatBlock, MessageOut, ProcessStep
from . import iso


def _conv_out(session: Session, c: Conversation) -> ConversationOut:
    count = session.query(func.count(Message.id)).filter_by(conversation_id=c.id, active=True).scalar() or 0
    return ConversationOut(
        id=c.id,
        project_id=c.project_id,
        title=c.title,
        pinned=c.pinned,
        archived=c.archived,
        provider=c.provider,
        model=c.model,
        last_message_at=iso(c.last_message_at),
        message_count=count,
        created_at=iso(c.created_at),
        updated_at=iso(c.updated_at),
    )


def list_conversations(
    session: Session, project_id: str, search: str | None = None, include_archived: bool = False
) -> list[ConversationOut]:
    q = session.query(Conversation).filter_by(project_id=project_id)
    if not include_archived:
        q = q.filter_by(archived=False)
    if search:
        like = f"%{search.lower()}%"
        # match on title or any message content in the conversation
        sub = (
            session.query(Message.conversation_id)
            .filter(func.lower(Message.content).like(like))
            .subquery()
        )
        q = q.filter(or_(func.lower(Conversation.title).like(like), Conversation.id.in_(sub)))
    convs = q.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).all()
    return [_conv_out(session, c) for c in convs]


def create_conversation(session: Session, project_id: str, title: str | None = None) -> Conversation:
    conv = Conversation(project_id=project_id, title=title or "New chat")
    session.add(conv)
    session.flush()
    return conv


def get_conversation(session: Session, conversation_id: str) -> Conversation | None:
    return session.get(Conversation, conversation_id)


def update_conversation(session: Session, conversation_id: str, **fields) -> Conversation | None:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        return None
    for key in ("title", "pinned", "archived", "draft"):
        if key in fields and fields[key] is not None:
            setattr(conv, key, fields[key])
    return conv


def delete_conversation(session: Session, conversation_id: str) -> None:
    conv = session.get(Conversation, conversation_id)
    if conv is not None:
        session.delete(conv)


def add_message(
    session: Session,
    conversation_id: str,
    role: str,
    content: str = "",
    blocks: list[dict] | None = None,
    process_steps: list[dict] | None = None,
    parent_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    usage: dict | None = None,
    skill: str | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        blocks=blocks or [],
        process_steps=process_steps or [],
        parent_id=parent_id,
        provider=provider,
        model=model,
        usage=usage,
        skill=skill,
    )
    session.add(msg)
    conv = session.get(Conversation, conversation_id)
    if conv is not None:
        conv.last_message_at = utcnow()
        if role == "user" and conv.title == "New chat" and content:
            conv.title = content.strip().splitlines()[0][:80]
    session.flush()
    return msg


def get_active_messages(session: Session, conversation_id: str) -> list[Message]:
    return (
        session.query(Message)
        .filter_by(conversation_id=conversation_id, active=True)
        .order_by(Message.created_at.asc())
        .all()
    )


def message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        role=m.role,
        content=m.content,
        blocks=[ChatBlock.model_validate(b) for b in (m.blocks or [])],
        process_steps=[ProcessStep.model_validate(s) for s in (m.process_steps or [])],
        parent_id=m.parent_id,
        created_at=iso(m.created_at),
        model=m.model,
        provider=m.provider,
        usage=m.usage,
    )


def branch_from_user_edit(session: Session, message_id: str, new_content: str) -> Message | None:
    """Edit a previous user message: deactivate it and everything after it, then
    append a new active user message forming a fresh branch (spec section 7)."""
    target = session.get(Message, message_id)
    if target is None or target.role != "user":
        return None
    newer = (
        session.query(Message)
        .filter(
            Message.conversation_id == target.conversation_id,
            Message.created_at >= target.created_at,
            Message.active.is_(True),
        )
        .all()
    )
    for m in newer:
        m.active = False
    return add_message(
        session,
        conversation_id=target.conversation_id,
        role="user",
        content=new_content,
        parent_id=target.parent_id,
    )
