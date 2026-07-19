"""Project-wide search across conversations, messages and artifacts.

A deliberately simple, robust case-insensitive LIKE search — it works on any
existing local SQLite database with no extra tables, triggers or manual steps.
Result sets are small (bounded per source + overall), so LIKE is plenty fast
for a local single-user database.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db.models import Artifact, Conversation, Message
from ..schemas.api import SearchResultOut
from . import iso

_SNIPPET_BEFORE = 40
_SNIPPET_LENGTH = 160


def _escape_like(q: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _snippet(text: str | None, q: str) -> str:
    """Excerpt of ``text`` centred on the first case-insensitive match of ``q``."""
    if not text:
        return ""
    flat = " ".join(text.split())  # collapse newlines/whitespace
    idx = flat.lower().find(q.lower())
    if idx < 0:
        return flat[:_SNIPPET_LENGTH] + ("…" if len(flat) > _SNIPPET_LENGTH else "")
    start = max(0, idx - _SNIPPET_BEFORE)
    end = min(len(flat), start + _SNIPPET_LENGTH)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(flat) else ""
    return f"{prefix}{flat[start:end]}{suffix}"


def global_search(session: Session, project_id: str, q: str, limit: int = 20) -> list[SearchResultOut]:
    """Search conversation titles, message content and artifact names/content.

    Results are merged across sources and sorted by recency (most recently
    updated first), truncated to ``limit``.
    """
    q = q.strip()
    if not q:
        return []
    limit = max(1, min(limit, 100))
    like = f"%{_escape_like(q.lower())}%"
    results: list[tuple[float, SearchResultOut]] = []

    def _sort_key(dt) -> float:  # noqa: ANN001
        return dt.timestamp() if dt is not None else 0.0

    convs = (
        session.query(Conversation)
        .filter(Conversation.project_id == project_id,
                func.lower(Conversation.title).like(like, escape="\\"))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .all()
    )
    for c in convs:
        results.append((_sort_key(c.updated_at), SearchResultOut(
            type="conversation", id=c.id, title=c.title,
            snippet=_snippet(c.title, q), updated_at=iso(c.updated_at),
        )))

    messages = (
        session.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.project_id == project_id,
                Message.active.is_(True),
                func.lower(Message.content).like(like, escape="\\"))
        .order_by(Message.updated_at.desc())
        .limit(limit)
        .all()
    )
    for m in messages:
        results.append((_sort_key(m.updated_at), SearchResultOut(
            type="message", id=m.id, conversation_id=m.conversation_id,
            title=m.conversation.title if m.conversation else "",
            snippet=_snippet(m.content, q), updated_at=iso(m.updated_at),
        )))

    artifacts = (
        session.query(Artifact)
        .filter(Artifact.project_id == project_id,
                or_(func.lower(Artifact.name).like(like, escape="\\"),
                    func.lower(Artifact.content).like(like, escape="\\")))
        .order_by(Artifact.updated_at.desc())
        .limit(limit)
        .all()
    )
    for a in artifacts:
        text = a.content if (a.content and q.lower() in a.content.lower()) else a.name
        results.append((_sort_key(a.updated_at), SearchResultOut(
            type="artifact", id=a.id, title=a.name,
            snippet=_snippet(text, q), updated_at=iso(a.updated_at),
        )))

    results.sort(key=lambda pair: pair[0], reverse=True)
    return [r for _, r in results[:limit]]
