"""Request/response DTOs for the narrated browser-agent endpoint (Phase 4).

These wrap the domain models in ``app.agent.computer_use.actions`` for the wire.
They are intentionally NOT registered in ``CANONICAL_MODELS`` — the extension is
a separate TypeScript codebase, not the schema-generated frontend, so these
shapes don't participate in the frontend drift check.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

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
    "AgentTeamEvent",
    "AgentTeamSessionRequest",
    "AgentTeamSessionResponse",
    "AgentTeamSessionStatus",
    "AgentTeamWorker",
    "AgentTeamWorkerStatus",
    "AgentStepRequest",
    "AgentStepResponse",
    "Action",
    "ActionResult",
    "AxNode",
    "Observation",
    "Step",
    "WorkbookContext",
]


class AgentTeamSessionStatus(str, Enum):
    """Lifecycle states for an ephemeral parallel-agent sandbox."""

    running = "running"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class AgentTeamWorkerStatus(str, Enum):
    """Lifecycle states for one role worker within a team session."""

    queued = "queued"
    running = "running"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class AgentTeamSessionRequest(CamelModel):
    """Start a bounded, read-only team of role-specific AI workers."""

    goal: str = Field(min_length=1, max_length=4_000)
    project_id: str | None = None
    agent_count: int = Field(default=3, ge=1, le=12)


class AgentTeamEvent(CamelModel):
    """A small activity-feed entry suitable for the sandbox live view."""

    id: str
    type: str
    message: str
    created_at: datetime
    agent_id: str | None = None


class AgentTeamWorker(CamelModel):
    """Public snapshot of one independent role worker."""

    id: str
    role: str
    assignment: str
    status: AgentTeamWorkerStatus
    progress: int = Field(ge=0, le=100)
    activity: str
    output: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AgentTeamSessionResponse(CamelModel):
    """Serializable point-in-time snapshot of an ephemeral team session."""

    id: str
    goal: str
    project_id: str | None = None
    status: AgentTeamSessionStatus
    agent_count: int = Field(ge=1, le=12)
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    agents: list[AgentTeamWorker] = Field(default_factory=list)
    events: list[AgentTeamEvent] = Field(default_factory=list)


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
