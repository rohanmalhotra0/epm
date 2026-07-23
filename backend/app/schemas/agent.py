"""Request/response DTOs for the narrated browser-agent endpoint (Phase 4).

These wrap the domain models in ``app.agent.computer_use.actions`` for the wire.
They are intentionally NOT registered in ``CANONICAL_MODELS`` — the extension is
a separate TypeScript codebase, not the schema-generated frontend, so these
shapes don't participate in the frontend drift check.
"""

from __future__ import annotations

from pydantic import Field

from ..agent.computer_use.actions import (
    Action,
    ActionResult,
    AxNode,
    Observation,
    Step,
    WorkbookContext,
)
from .common import CamelModel

__all__ = [
    "AgentStepRequest",
    "AgentStepResponse",
    "Action",
    "ActionResult",
    "AxNode",
    "Observation",
    "Step",
    "WorkbookContext",
]


class AgentStepRequest(CamelModel):
    """One turn of the loop: the goal, the current page observation, and the
    steps taken so far (so the backend stays stateless / restart-safe — the
    extension's service worker owns the session state)."""

    goal: str
    observation: Observation
    history: list[Step] = Field(default_factory=list)
    # Optional project id — selects that project's active provider (owner-scoped);
    # otherwise the globally active provider is used.
    project_id: str | None = None
    # Optional explicit model override (e.g. pin a vision model for a screenshot
    # step). Normally left unset — the provider routes by role.
    model: str | None = None
    # Optional Excel context selected in the extension. The content is produced
    # by the parse-only inspector and is never interpreted or executed here.
    workbook_context: WorkbookContext | None = None


class AgentStepResponse(CamelModel):
    """Non-streaming counterpart of the SSE endpoint (handy for tests/tools)."""

    step: Step
