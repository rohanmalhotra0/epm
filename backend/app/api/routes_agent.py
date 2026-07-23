"""Narrated browser-agent endpoint (Phase 4 — the headline feature).

The MV3 Chrome extension runs the outer plan→act→observe loop; this endpoint is
one **step** of it: it takes an accessibility-tree observation (+ optional
screenshot data URL) and streams the agent's narration followed by the next
structured action.

Transport is SSE via ``StreamingResponse``, mirroring
``routes_conversations.py``. Owner-scoped via ``get_current_owner``. The backend
is stateless across steps — the extension's service worker owns session state
and replays ``history`` — so an MV3 worker restart never loses the plan.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..agent.computer_use import decide_step, stream_step
from ..ai.base import AIProvider, ProviderError
from ..ai.registry import resolve_active_provider
from ..db.base import get_sessionmaker
from ..schemas.agent import AgentStepRequest, AgentStepResponse
from .deps import authorize_project_id, get_current_owner, get_db

router = APIRouter(tags=["agent"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _resolve_provider_for(owner: str, project_id: str | None) -> AIProvider:
    """Resolve the active provider in a short-lived session that is closed
    before any streaming begins (no DB transaction is held across the stream).
    Ownership of the named project is enforced first."""
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        if project_id:
            authorize_project_id(session, owner, project_id)
        _profile, provider = resolve_active_provider(session, project_id)
        return provider
    finally:
        session.close()


async def _stream(provider: AIProvider, body: AgentStepRequest) -> AsyncIterator[str]:
    index = len(body.history)
    yield _sse("start", {"index": index, "goal": body.goal})
    try:
        async for out in stream_step(provider, body.goal, body.observation, body.history,
                                     workbook_context=body.workbook_context,
                                     index=index, model=body.model):
            if out.kind == "token" and out.text:
                yield _sse("token", {"text": out.text})
            elif out.kind == "step" and out.step is not None:
                yield _sse("step", out.step.model_dump(by_alias=True))
    except ProviderError as exc:
        yield _sse("error", {"message": exc.message, "category": exc.category})
    except Exception as exc:  # never leave the client without a terminal event
        yield _sse("error", {"message": str(exc)[:300]})
    yield _sse("done", {})


@router.post("/api/agent/step")
def agent_step_stream(body: AgentStepRequest,
                      owner: str = Depends(get_current_owner)) -> StreamingResponse:
    """Stream the next agent step as SSE: ``start`` → ``token``* → ``step`` → ``done``."""
    provider = _resolve_provider_for(owner, body.project_id)
    return StreamingResponse(
        _stream(provider, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/api/agent/step/once", response_model=AgentStepResponse)
async def agent_step_once(body: AgentStepRequest,
                          session: Session = Depends(get_db),
                          owner: str = Depends(get_current_owner)) -> AgentStepResponse:
    """Non-streaming single step (handy for tools/tests and simple clients)."""
    if body.project_id:
        authorize_project_id(session, owner, body.project_id)
    _profile, provider = resolve_active_provider(session, body.project_id)
    step = await decide_step(provider, body.goal, body.observation, body.history,
                             workbook_context=body.workbook_context,
                             index=len(body.history), model=body.model)
    return AgentStepResponse(step=step)
