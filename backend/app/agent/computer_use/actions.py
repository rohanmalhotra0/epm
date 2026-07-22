"""Typed action / observation / step models for the narrated browser agent.

These are the deterministic, well-typed contract between:

* the **Chrome extension** — which produces an :class:`Observation` (an
  accessibility-tree snapshot with stable ``ref`` ids + an optional screenshot
  data URL) and executes an :class:`Action`, and
* the **backend agent loop** — which consumes an ``Observation`` and returns the
  next ``Action`` plus a human ``narration`` string (a :class:`Step`).

Grounding follows the Chrome-extension research (see ``docs/OPENCLAW_PLAN.md`` §6):
the **accessibility tree with ``ref`` ids is the primary grounding** (target
``ref=42`` not pixels); coordinates and screenshots are the fallback for
canvas / ARIA-poor views (e.g. Oracle ADF/JET grids).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for the agent wire models: camelCase JSON, snake_case Python.

    Unlike ``app.schemas.common.CamelModel`` this deliberately does NOT set
    ``use_enum_values`` (so ``action.type`` stays a real ``ActionType`` member,
    which the loop compares by identity) and does NOT forbid extra keys (so a
    slightly-verbose model response is tolerated rather than rejected).
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ActionType(str, Enum):
    """The low-level action vocabulary the extension can execute.

    Deliberately small — this is a scaffold. Oracle-specific compound gestures
    (grid cell edit, POV member picker, iframe drill) are *composed* from these
    primitives by the agent loop; they are NOT new action types here.
    """

    click = "click"
    type = "type"          # noqa: A003 - matches the wire vocabulary
    scroll = "scroll"
    navigate = "navigate"
    screenshot = "screenshot"
    wait = "wait"
    done = "done"


class Action(CamelModel):
    """A single low-level action, grounded by ``ref`` (primary) or ``x/y`` (fallback).

    Exactly which fields are required depends on ``type`` — see the validator.
    """

    type: ActionType
    # Accessibility-tree ref id — the PRIMARY grounding. ``click ref=42``.
    ref: int | None = None
    # Coordinate fallback for canvas / ARIA-poor regions (screenshot-grounded).
    x: int | None = None
    y: int | None = None
    # ``type`` payload.
    text: str | None = None
    # ``navigate`` payload.
    url: str | None = None
    # ``scroll`` payload (pixels; positive = down / right).
    delta_x: int = 0
    delta_y: int = 0
    # ``wait`` payload (milliseconds).
    duration_ms: int | None = None
    # Model's short machine-facing rationale (distinct from the user narration).
    reason: str | None = None

    @property
    def has_ref(self) -> bool:
        return self.ref is not None

    @property
    def has_coords(self) -> bool:
        return self.x is not None and self.y is not None

    @model_validator(mode="after")
    def _validate_shape(self) -> Action:
        t = self.type
        if t in (ActionType.click,) and not (self.has_ref or self.has_coords):
            raise ValueError("click requires a `ref` (preferred) or `x`+`y` coordinates")
        if t is ActionType.type:
            if self.text is None:
                raise ValueError("type requires `text`")
            if not (self.has_ref or self.has_coords):
                raise ValueError("type requires a `ref` (preferred) or `x`+`y` coordinates")
        if t is ActionType.navigate and not self.url:
            raise ValueError("navigate requires a `url`")
        return self


class AxNode(CamelModel):
    """One node of the flattened accessibility-tree snapshot.

    ``ref`` is the stable id the extension assigns and can resolve back to a DOM
    element; the loop refers to elements exclusively by ``ref``.
    """

    ref: int
    role: str                       # button | textbox | link | cell | ...
    name: str = ""                  # accessible name
    value: str | None = None        # current value for inputs
    focused: bool = False
    disabled: bool = False
    # Optional viewport rectangle [x, y, w, h] — enables the coordinate fallback.
    rect: list[int] | None = None


class Observation(CamelModel):
    """The page state captured by the content script for one agent turn."""

    url: str = ""
    title: str = ""
    # Flattened accessibility tree — the primary grounding surface.
    nodes: list[AxNode] = []
    # Optional screenshot as a data URL (``data:image/png;base64,...``); the
    # FALLBACK grounding, routed to the provider's vision role model.
    screenshot: str | None = None
    # Free-form notes the content script wants the model to know (e.g. "iframe").
    notes: str | None = None

    @property
    def has_screenshot(self) -> bool:
        return bool(self.screenshot)


class Step(CamelModel):
    """One plan→act→observe→narrate cycle result.

    ``narration`` is the human-facing "watch it work" commentary shown (and
    optionally spoken) in the side panel. ``action`` is what to execute next.
    """

    index: int = 0
    narration: str
    action: Action
    # Whether the loop believes the goal is met (mirrors action.type == done).
    done: bool = False
    # Raw model text, kept for debugging / transcript. Not shown to the user.
    raw: str | None = None
