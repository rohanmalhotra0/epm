"""The plan→act→observe→narrate loop step.

The extension owns the outer loop (capture → send → execute → repeat); the
backend owns a **single deterministic step**: given ``(goal, observation,
history)`` it calls the active provider and returns the next :class:`Step`
(action + narration).

Determinism: given the same provider output text, action extraction and the
resulting ``Step`` are a pure function of the inputs. The network/model itself
is the only non-deterministic part, and it is injected (``AIProvider``), so
tests use the deterministic ``MockProvider`` or a scripted stub.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ...ai.base import AIMessage, AIProvider, TextDelta
from .actions import Action, ActionType, Observation, Step, WorkbookContext
from .prompt import SYSTEM_PROMPT, format_goal, format_observation, format_workbook_context

# How many prior steps to include as context. Kept small — the loop is
# observation-driven, not transcript-driven.
_HISTORY_LIMIT = 12


def build_messages(
    goal: str,
    observation: Observation,
    history: list[Step],
    workbook_context: WorkbookContext | None = None,
) -> list[AIMessage]:
    """Assemble the provider messages for one step.

    A screenshot on the observation is attached via ``AIMessage.images`` so the
    OpenAI-compatible provider routes the turn to its "vision" role model
    (see ``app/ai/openai_compat.py``). Text-only observations keep the plain
    wire shape.
    """
    messages: list[AIMessage] = [AIMessage(role="user", content=format_goal(goal))]
    if workbook_context is not None:
        messages.append(AIMessage(role="user", content=format_workbook_context(workbook_context)))
    for step in history[-_HISTORY_LIMIT:]:
        messages.append(AIMessage(role="assistant", content=_step_summary(step)))
    obs_text = format_observation(observation)
    images = [observation.screenshot] if observation.screenshot else []
    messages.append(AIMessage(role="user", content=obs_text, images=images))
    return messages


def _step_summary(step: Step) -> str:
    payload: dict[str, object] = {
        "narration": step.narration,
        "action": step.action.model_dump(
            by_alias=True,
            exclude_none=True,
            exclude_defaults=True,
        ),
    }
    if step.result is not None:
        payload["result"] = step.result.model_dump(by_alias=True, exclude_none=True)
    return json.dumps(payload, default=str, separators=(",", ":"))


def extract_action_json(text: str) -> dict | None:
    """Extract the first balanced top-level JSON object from ``text``.

    Robust to models that wrap the JSON in prose or ```json fences. Returns the
    parsed dict, or ``None`` if no parseable object is found. Deterministic.
    """
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        start = -1  # keep scanning for the next object
    return None


def parse_step(raw: str, index: int) -> Step:
    """Turn raw model text into a validated :class:`Step`.

    Falls back gracefully: if no valid action JSON is present (e.g. the
    deterministic ``MockProvider`` returns prose), it degrades to a
    ``screenshot`` action so the outer loop can re-observe rather than crash.
    This keeps the scaffold robust with any provider.
    """
    obj = extract_action_json(raw)
    if obj and isinstance(obj.get("action"), dict):
        narration = str(obj.get("narration") or "").strip() or "(no narration)"
        try:
            action = Action.model_validate(obj["action"])
        except Exception:
            action = _fallback_action(raw)
            narration = narration or "I couldn't form a valid action; taking a screenshot to look again."
    elif obj and obj.get("type"):
        # The model returned a bare action object (no wrapper).
        try:
            action = Action.model_validate(obj)
            narration = (action.reason or "Working on the next step.").strip()
        except Exception:
            action = _fallback_action(raw)
            narration = "I couldn't form a valid action; taking a screenshot to look again."
    else:
        action = _fallback_action(raw)
        narration = "I need a clearer view of the page, so I'll take a screenshot."
    return Step(index=index, narration=narration, action=action,
                done=action.type is ActionType.done, raw=raw)


def _fallback_action(raw: str) -> Action:
    return Action(type=ActionType.screenshot, reason="fallback: no valid action parsed")


async def decide_step(
    provider: AIProvider,
    goal: str,
    observation: Observation,
    history: list[Step] | None = None,
    *,
    workbook_context: WorkbookContext | None = None,
    index: int = 0,
    model: str | None = None,
    max_tokens: int = 256,
) -> Step:
    """Produce the next :class:`Step` (non-streaming). Used by tests and callers
    that don't need token-level narration streaming."""
    history = history or []
    messages = build_messages(goal, observation, history, workbook_context)
    raw = await provider.complete(messages, system=SYSTEM_PROMPT, model=model,
                                  temperature=0.0, max_tokens=max_tokens)
    return parse_step(raw, index)


@dataclass
class StreamChunkOut:
    """A streamed loop output: either a raw token (``token``) or the final,
    parsed step (``step``). The route serialises these to SSE."""

    kind: str  # "token" | "step"
    text: str | None = None
    step: Step | None = None


async def stream_step(
    provider: AIProvider,
    goal: str,
    observation: Observation,
    history: list[Step] | None = None,
    *,
    workbook_context: WorkbookContext | None = None,
    index: int = 0,
    model: str | None = None,
    max_tokens: int = 256,
) -> AsyncIterator[StreamChunkOut]:
    """Stream a step: raw model tokens as they arrive (so the panel shows the
    agent 'thinking'), then a single terminal parsed :class:`Step`.

    NOTE (scaffold): narration and action share one JSON object, so we stream
    the raw text for liveness and emit clean structured narration only at the
    end. A future refactor can split narration/action into two model calls (or
    a tool-call) for smoother token-level narration.
    """
    history = history or []
    messages = build_messages(goal, observation, history, workbook_context)
    parts: list[str] = []
    async for chunk in provider.stream(messages, system=SYSTEM_PROMPT, model=model,
                                       temperature=0.0, max_tokens=max_tokens):
        if isinstance(chunk, TextDelta):
            parts.append(chunk.text)
            yield StreamChunkOut(kind="token", text=chunk.text)
    raw = "".join(parts)
    yield StreamChunkOut(kind="step", step=parse_step(raw, index))
