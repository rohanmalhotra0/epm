"""Token-gated ``/api/ext`` routes for the browser-agent extension.

These endpoints sit OUTSIDE the interactive login gate (oauth2-proxy is
configured to skip auth for ``^/api/ext``) so the extension can drive the agent
autonomously — without a signed-in website tab. Identity comes ONLY from a valid
``Authorization: Bearer epmw_…`` token (see ``get_owner_from_token``); a
client-supplied identity header is never trusted here.

Functionally ``/api/ext/agent/step`` mirrors ``/api/agent/step`` — it reuses the
same provider resolution and SSE streaming — differing only in how the owner is
authenticated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from ..schemas.agent import AgentStepRequest
from ..spreadsheet import WorkbookInspection
from .deps import get_owner_from_token
from .routes_agent import _resolve_provider_for, _stream
from .routes_spreadsheet import run_inspection

router = APIRouter(prefix="/api/ext", tags=["ext"])


@router.get("/whoami")
def whoami(owner: str = Depends(get_owner_from_token)) -> dict:
    """Lightweight auth check for the extension's "Test connection" button.
    200 + the resolved owner when the token is valid; 401 otherwise."""
    return {"ok": True, "owner": owner}


@router.post("/agent/step")
def ext_agent_step_stream(body: AgentStepRequest,
                          owner: str = Depends(get_owner_from_token)) -> StreamingResponse:
    """Autonomous twin of ``POST /api/agent/step`` — token-authenticated."""
    provider = _resolve_provider_for(owner, body.project_id)
    return StreamingResponse(
        _stream(provider, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/spreadsheet/inspect", response_model=WorkbookInspection)
async def ext_inspect_workbook(file: UploadFile = File(...),
                               _owner: str = Depends(get_owner_from_token)) -> WorkbookInspection:
    """Autonomous twin of ``POST /api/spreadsheet/inspect`` — token-authenticated."""
    return await run_inspection(file)
