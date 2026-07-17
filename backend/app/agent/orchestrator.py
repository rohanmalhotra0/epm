"""Chat orchestrator (spec sections 7, 8).

Selects a skill (respecting an active workflow), runs it while streaming process
steps / tokens / typed blocks, then persists the assistant message and any
workflow state. Deterministic skills own the pipeline; the model assists with
prose where a skill delegates to it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from ..connector.base import EpmConnector
from ..connector.errors import ConnectorError
from ..db.models import Conversation, Project, WorkflowState
from ..logging import get_logger
from ..schemas.chat import ChatBlock, StreamEvent, StreamEventType
from ..schemas.form_spec import FormSpecification
from ..security.redaction import looks_like_secret
from ..services import conversations as conv_svc
from . import blocks as B
from .intent import detect_intent
from .skills import WORKFLOW_SKILLS, SkillContext, SkillResult, get_skill
from .skills.base import Emitter
from .tools import ToolContext

log = get_logger(__name__)
_SWITCH_INTENTS = {"rules", "context", "forms", "reports"}


class _QueueEmitter(Emitter):
    """Streams to an asyncio.Queue while accumulating the final message."""

    def __init__(self, queue: asyncio.Queue) -> None:
        super().__init__()
        self._queue = queue
        self.text_parts: list[str] = []
        self.blocks: list[ChatBlock] = []

    async def emit_process(self) -> None:
        await self._queue.put(StreamEvent(type=StreamEventType.process,
                                          data={"steps": [s.model_dump(by_alias=True) for s in self.process]}))

    async def token(self, text: str) -> None:
        self.text_parts.append(text)
        await self._queue.put(StreamEvent(type=StreamEventType.token, data={"text": text}))

    async def block(self, block: ChatBlock) -> None:
        for i, existing in enumerate(self.blocks):
            if existing.id == block.id:
                self.blocks[i] = block
                break
        else:
            self.blocks.append(block)
        await self._queue.put(StreamEvent(type=StreamEventType.block, data=block.model_dump(by_alias=True)))


def _active_workflow(session: Session, conversation_id: str) -> WorkflowState | None:
    return (session.query(WorkflowState)
            .filter_by(conversation_id=conversation_id, active=True)
            .order_by(WorkflowState.updated_at.desc()).first())


def _active_form_spec(wf: WorkflowState | None) -> FormSpecification | None:
    if wf and wf.skill == "forms" and wf.data and wf.data.get("spec"):
        try:
            return FormSpecification.model_validate(wf.data["spec"])
        except Exception:
            return None
    return None


def _route(session: Session, conversation: Conversation, user_text: str) -> tuple[str, WorkflowState | None]:
    intent = detect_intent(user_text)
    active_wf = _active_workflow(session, conversation.id)
    if active_wf and active_wf.skill in WORKFLOW_SKILLS:
        if intent.is_slash and intent.skill not in WORKFLOW_SKILLS:
            active_wf.active = False
            return intent.skill, None
        if (not intent.is_slash) and intent.skill in _SWITCH_INTENTS:
            active_wf.active = False
            return intent.skill, None
        return active_wf.skill, active_wf
    return intent.skill, active_wf if (active_wf and active_wf.skill == intent.skill) else None


def _upsert_workflow(session: Session, conversation: Conversation, result: SkillResult) -> None:
    if not result.workflow_active and result.workflow_state is None:
        return
    row = (session.query(WorkflowState)
           .filter_by(conversation_id=conversation.id, skill=result.skill).first())
    if row is None:
        row = WorkflowState(conversation_id=conversation.id, project_id=conversation.project_id,
                            skill=result.skill, state=result.workflow_state or "", data=result.workflow_data or {},
                            active=result.workflow_active)
        session.add(row)
    else:
        row.state = result.workflow_state or row.state
        row.data = result.workflow_data if result.workflow_data is not None else row.data
        row.active = result.workflow_active


async def stream_turn(
    *,
    session: Session,
    project: Project,
    conversation: Conversation,
    connector: EpmConnector,
    provider,
    application: str,
    classification: str,
    environment_name: str,
    demo: bool,
    context_version_id: str | None,
    user_text: str,
) -> AsyncIterator[StreamEvent]:
    queue: asyncio.Queue = asyncio.Queue()
    emit = _QueueEmitter(queue)

    skill_name, workflow = _route(session, conversation, user_text)
    active_form_spec = _active_form_spec(_active_workflow(session, conversation.id) or workflow)

    tool_ctx = ToolContext(session=session, project=project, connector=connector, application=application,
                           context_version_id=context_version_id, conversation_id=conversation.id)
    skill_ctx = SkillContext(
        session=session, project=project, conversation=conversation, connector=connector,
        application=application, provider=provider, user_text=user_text,
        intent=detect_intent(user_text), tool_ctx=tool_ctx, classification=classification,
        environment_name=environment_name, demo=demo, context_version_id=context_version_id,
        workflow=workflow, active_form_spec=active_form_spec,
    )

    if looks_like_secret(user_text):
        await emit.block(B.error_diagnostics({
            "category": "security",
            "message": "Your message looked like it might contain a secret (API key or password).",
            "suggestedAction": "Secrets are never sent to the model. Configure credentials in Settings instead.",
        }))

    result_holder: dict[str, SkillResult] = {}

    async def _run() -> None:
        skill = get_skill(skill_name)
        try:
            result_holder["result"] = await skill.run(skill_ctx, emit)
        except ConnectorError as exc:
            await emit.block(B.error_diagnostics({**exc.to_dict()}))
            result_holder["result"] = SkillResult(skill=skill_name)
        except Exception as exc:  # normalise anything unexpected
            log.error("skill_error", skill=skill_name, error=str(exc))
            await emit.block(B.error_diagnostics({
                "category": "artifactGeneration", "message": "Something went wrong handling that request.",
                "technicalDetail": str(exc)[:300],
                "suggestedAction": "Try rephrasing, or check Diagnostics.",
            }))
            result_holder["result"] = SkillResult(skill=skill_name)
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(_run())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    result = result_holder.get("result") or SkillResult(skill=skill_name)

    # persist the assistant message + workflow state
    message = conv_svc.add_message(
        session, conversation.id, role="assistant",
        content="".join(emit.text_parts),
        blocks=[b.model_dump(by_alias=True) for b in emit.blocks],
        process_steps=[s.model_dump(by_alias=True) for s in emit.process],
        provider=result.provider_used or getattr(provider, "name", None),
        model=result.model_used,
        usage=result.usage,
        skill=result.skill,
    )
    conversation.provider = getattr(provider, "name", conversation.provider)
    _upsert_workflow(session, conversation, result)
    session.flush()

    yield StreamEvent(type=StreamEventType.message_saved, data={"messageId": message.id, "title": conversation.title})
    yield StreamEvent(type=StreamEventType.done, data={"skill": result.skill})
