"""Computer-use / narrated browser agent loop (Phase 4).

The deterministic backend half of the MV3 Chrome extension's plan→act→observe→
narrate loop. See ``docs/OPENCLAW_PLAN.md`` §6 and ``extension/README.md``.
"""

from __future__ import annotations

from .actions import Action, ActionResult, ActionType, AxNode, Observation, Step, WorkbookContext
from .loop import StreamChunkOut, decide_step, extract_action_json, parse_step, stream_step
from .prompt import SYSTEM_PROMPT, format_observation

__all__ = [
    "Action",
    "ActionResult",
    "ActionType",
    "AxNode",
    "Observation",
    "Step",
    "WorkbookContext",
    "StreamChunkOut",
    "decide_step",
    "stream_step",
    "parse_step",
    "extract_action_json",
    "SYSTEM_PROMPT",
    "format_observation",
]
