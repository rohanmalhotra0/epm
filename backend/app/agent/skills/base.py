"""Skill framework (spec section 35).

A skill is an independently-testable deterministic workflow. It streams process
steps, tokens and typed blocks through an ``Emitter`` and returns a
``SkillResult`` describing any persisted workflow state. The orchestrator selects
a skill (via intent) and runs it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ...ai.base import AIProvider
from ...connector.base import EpmConnector
from ...db.models import Conversation, Project, WorkflowState
from ...schemas.chat import ChatBlock, ProcessStep, ProcessStepState
from ...schemas.tools import SkillSpec
from ..intent import Intent
from ..tools import ToolContext


@dataclass
class SkillContext:
    session: Session
    project: Project
    conversation: Conversation
    connector: EpmConnector
    application: str
    provider: AIProvider
    user_text: str
    intent: Intent
    tool_ctx: ToolContext
    classification: str = "development"
    environment_name: str = "Demo"
    demo: bool = True
    context_version_id: str | None = None
    workflow: WorkflowState | None = None
    active_form_spec: object | None = None  # FormSpecification of an in-progress form, if any


class Emitter(ABC):
    """Streams events to the client while accumulating the final message."""

    def __init__(self) -> None:
        self.process: list[ProcessStep] = []

    @abstractmethod
    async def emit_process(self) -> None: ...

    @abstractmethod
    async def token(self, text: str) -> None: ...

    @abstractmethod
    async def block(self, block: ChatBlock) -> None: ...

    def set_steps(self, steps: list[ProcessStep]) -> None:
        self.process = steps

    def mark(self, index: int, state: ProcessStepState) -> None:
        if 0 <= index < len(self.process):
            self.process[index].state = state

    async def step_running(self, index: int) -> None:
        self.mark(index, ProcessStepState.active)
        await self.emit_process()

    async def step_done(self, index: int) -> None:
        self.mark(index, ProcessStepState.done)
        await self.emit_process()

    async def prose(self, text: str) -> None:
        """Stream a block of prose as word chunks (nicer incremental UI)."""
        chunk = ""
        for ch in text:
            chunk += ch
            if ch in " \n" and len(chunk) >= 6:
                await self.token(chunk)
                chunk = ""
        if chunk:
            await self.token(chunk)

    async def stream_provider_text(self, ctx: SkillContext, messages, system: str | None = None) -> str:
        from ...ai.base import TextDelta
        parts: list[str] = []
        async for chunk in ctx.provider.stream(messages, system=system, max_tokens=800):
            if isinstance(chunk, TextDelta):
                parts.append(chunk.text)
                await self.token(chunk.text)
        return "".join(parts)


@dataclass
class SkillResult:
    skill: str
    workflow_state: str | None = None
    workflow_data: dict | None = None
    workflow_active: bool = False
    handled: bool = True
    provider_used: str | None = None
    model_used: str | None = None
    usage: dict | None = None


class Skill(ABC):
    spec: SkillSpec

    @abstractmethod
    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult: ...
