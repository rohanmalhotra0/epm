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
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ...ai.base import AIMessage, AIProvider, TextDelta
from .actions import Action, ActionType, Observation, Step, WorkbookContext
from .prompt import SYSTEM_PROMPT, format_goal, format_observation, format_workbook_context

# How many prior steps to include as context. Kept small — the loop is
# observation-driven, not transcript-driven.
_HISTORY_LIMIT = 12
_BLOCKED_PREFIX = "blocked:"
_GOAL_STOP_WORDS = {
    "able",
    "agent",
    "and",
    "at",
    "be",
    "can",
    "could",
    "find",
    "for",
    "infer",
    "in",
    "it",
    "look",
    "of",
    "on",
    "open",
    "page",
    "please",
    "should",
    "show",
    "the",
    "this",
    "to",
    "view",
    "want",
}
_CLICKABLE_ROLES = {
    "button",
    "cell",
    "gridcell",
    "link",
    "menuitem",
    "option",
    "row",
    "tab",
    "treeitem",
}


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


def parse_step(
    raw: str,
    index: int,
    *,
    observation: Observation | None = None,
    history: list[Step] | None = None,
) -> Step:
    """Turn raw model text into a validated :class:`Step`.

    Falls back gracefully: if no valid action JSON is present (e.g. the
    deterministic ``MockProvider`` returns prose), it degrades to a
    ``screenshot`` action so the outer loop can re-observe rather than crash.
    This keeps the scaffold robust with any provider.
    """
    history = history or []
    obj = extract_action_json(raw)
    if obj and isinstance(obj.get("action"), dict):
        narration = str(obj.get("narration") or "").strip() or "(no narration)"
        try:
            action = Action.model_validate(obj["action"])
        except Exception:
            action, narration = _fallback_step(observation, history)
    elif obj and obj.get("type"):
        # The model returned a bare action object (no wrapper).
        try:
            action = Action.model_validate(obj)
            narration = (action.reason or "Working on the next step.").strip()
        except Exception:
            action, narration = _fallback_step(observation, history)
    else:
        action, narration = _fallback_step(observation, history)

    # A model asking for another screenshot while it already has the current
    # image cannot gain new evidence. Stop cleanly instead of creating an
    # unbounded screenshot → parse fallback → screenshot loop.
    if action.type is ActionType.screenshot and (
        observation is not None and observation.has_screenshot
        or history and history[-1].action.type is ActionType.screenshot
    ):
        action = Action(
            type=ActionType.done,
            reason="blocked: repeated screenshot request produced no grounded action",
        )
        narration = (
            "I can see the captured page, but I couldn't ground a reliable next "
            "action from it. I am stopping instead of repeating screenshots."
        )
    return Step(index=index, narration=narration, action=action,
                done=action.type is ActionType.done, raw=raw)


def _fallback_step(
    observation: Observation | None,
    history: list[Step],
) -> tuple[Action, str]:
    already_visual = bool(observation and observation.has_screenshot)
    just_requested_visual = bool(
        history and history[-1].action.type is ActionType.screenshot
    )
    if already_visual or just_requested_visual:
        return (
            Action(
                type=ActionType.done,
                reason="blocked: vision response did not contain a valid action",
            ),
            "I received the page image, but the vision response did not contain "
            "a usable action. I am stopping instead of looping on screenshots.",
        )
    return (
        Action(type=ActionType.screenshot, reason="fallback: no valid action parsed"),
        "I need a clearer view of the page, so I'll take a screenshot.",
    )


def _meaningful_terms(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) >= 3 and word not in _GOAL_STOP_WORDS
    }


def _goal_match_score(goal_terms: set[str], label: str) -> int:
    label_terms = _meaningful_terms(label)
    return sum(
        any(
            label_term == goal_term
            or label_term.startswith(goal_term)
            or goal_term.startswith(label_term)
            for label_term in label_terms
        )
        for goal_term in goal_terms
    )


def _grounding_issue(
    step: Step,
    observation: Observation,
    goal: str,
) -> str | None:
    """Return why a model step cannot be executed against this observation."""
    reason = (step.action.reason or "").strip()
    if (
        step.action.type is ActionType.done
        and reason.lower().startswith(_BLOCKED_PREFIX)
    ):
        return reason[len(_BLOCKED_PREFIX):].strip() or "no usable action was produced"

    if step.action.ref is not None:
        nodes_by_ref = {node.ref: node for node in observation.nodes}
        if step.action.ref not in nodes_by_ref:
            goal_terms = _meaningful_terms(goal)
            candidates = [
                node
                for node in observation.nodes
                if (
                    not node.disabled
                    and node.name
                    and node.role.lower() in _CLICKABLE_ROLES
                )
            ]
            if len(goal_terms) >= 2 and candidates:
                best = max(
                    candidates,
                    key=lambda node: _goal_match_score(goal_terms, node.name),
                )
                best_score = _goal_match_score(goal_terms, best.name)
                if best_score >= 2:
                    return (
                        f"ref {step.action.ref} is not in the current snapshot; "
                        f"visible ref {best.ref} ({best.name!r}) matches "
                        f"{best_score} meaningful goal terms"
                    )
            return (
                f"ref {step.action.ref} is not present in the current accessibility "
                "snapshot"
            )

        # Resolve ambiguous result lists deterministically. For a goal such as
        # "Open SOFR Loan", a short visible item named "SOFR" is only a partial
        # match when "SOFR-LoanBalance" is also present. This check does not
        # auto-click; it asks the model to correct the action using the better
        # current ref.
        if step.action.type is ActionType.click:
            goal_terms = _meaningful_terms(goal)
            target = nodes_by_ref[step.action.ref]
            target_score = _goal_match_score(goal_terms, target.name)
            candidates = [
                node
                for node in observation.nodes
                if (
                    node.ref != target.ref
                    and not node.disabled
                    and node.name
                    and node.role.lower() in _CLICKABLE_ROLES
                )
            ]
            if len(goal_terms) >= 2 and candidates:
                best = max(
                    candidates,
                    key=lambda node: _goal_match_score(goal_terms, node.name),
                )
                best_score = _goal_match_score(goal_terms, best.name)
                if best_score >= 2 and best_score > target_score:
                    return (
                        f"ref {target.ref} ({target.name!r}) matches only "
                        f"{target_score} meaningful goal terms, while visible "
                        f"ref {best.ref} ({best.name!r}) matches {best_score}"
                    )
    return None


def _repair_messages(
    messages: list[AIMessage],
    raw: str,
    issue: str,
) -> list[AIMessage]:
    previous = raw.strip()[:4000] or "(empty response)"
    return [
        *messages,
        AIMessage(role="assistant", content=previous),
        AIMessage(
            role="user",
            content=(
                "CORRECTION REQUIRED: The previous action could not be executed "
                f"because {issue}. Return one corrected JSON action now. Reuse only "
                "a ref that appears in the current ACCESSIBILITY TREE. If the target "
                "is visible only in the attached screenshot, click it with x/y image "
                "coordinates and set coordinateSpace to \"image\". Do not request "
                "another screenshot, and do not return done unless the goal is "
                "visibly complete."
            ),
        ),
    ]


def _blocked_after_repair(raw: str, index: int, issue: str) -> Step:
    return Step(
        index=index,
        narration=(
            "I can see the page, but I still could not produce an executable "
            "grounded action after correcting the vision response."
        ),
        action=Action(
            type=ActionType.done,
            reason=f"blocked: {issue}",
        ),
        done=True,
        raw=raw,
    )


async def _repair_step_once(
    provider: AIProvider,
    messages: list[AIMessage],
    step: Step,
    raw: str,
    *,
    goal: str,
    observation: Observation,
    history: list[Step],
    index: int,
    model: str | None,
    max_tokens: int,
) -> Step:
    """Make one bounded correction attempt for malformed or stale grounding."""
    issue = _grounding_issue(step, observation, goal)
    if issue is None:
        return step

    repaired_raw = await provider.complete(
        _repair_messages(messages, raw, issue),
        system=SYSTEM_PROMPT,
        model=model,
        temperature=0.0,
        max_tokens=max_tokens,
    )
    repaired = parse_step(
        repaired_raw,
        index,
        observation=observation,
        history=history,
    )
    remaining_issue = _grounding_issue(repaired, observation, goal)
    if remaining_issue is not None:
        return _blocked_after_repair(repaired_raw, index, remaining_issue)
    return repaired


async def decide_step(
    provider: AIProvider,
    goal: str,
    observation: Observation,
    history: list[Step] | None = None,
    *,
    workbook_context: WorkbookContext | None = None,
    index: int = 0,
    model: str | None = None,
    max_tokens: int = 512,
) -> Step:
    """Produce the next :class:`Step` (non-streaming). Used by tests and callers
    that don't need token-level narration streaming."""
    history = history or []
    messages = build_messages(goal, observation, history, workbook_context)
    raw = await provider.complete(messages, system=SYSTEM_PROMPT, model=model,
                                  temperature=0.0, max_tokens=max_tokens)
    step = parse_step(raw, index, observation=observation, history=history)
    return await _repair_step_once(
        provider,
        messages,
        step,
        raw,
        goal=goal,
        observation=observation,
        history=history,
        index=index,
        model=model,
        max_tokens=max_tokens,
    )


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
    max_tokens: int = 512,
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
    step = parse_step(raw, index, observation=observation, history=history)
    step = await _repair_step_once(
        provider,
        messages,
        step,
        raw,
        goal=goal,
        observation=observation,
        history=history,
        index=index,
        model=model,
        max_tokens=max_tokens,
    )
    yield StreamChunkOut(
        kind="step",
        step=step,
    )
