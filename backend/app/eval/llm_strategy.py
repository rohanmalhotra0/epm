"""LLM-proposes / deterministic-validates strategy for the eval harness.

The model only ever *proposes* a ``FormSpecification`` as JSON; everything that
makes the answer trustworthy stays deterministic — Pydantic parses and validates
the proposal, the scorer's ``validate_form`` checks it against real tenant
metadata, and a malformed or off-schema response is raised (the runner counts it
as an errored case, never a crash). Run the identical golden corpus through
:class:`LlmStrategy` and :class:`DeterministicStrategy` and the coverage delta is
the bake-off verdict.

The completion function is dependency-injected (``complete(system, user) ->
text``), so tests drive the whole parse → validate → score pipeline with fakes
and never touch a network; :func:`provider_complete` builds a real one from any
registered ``AIProvider`` (Ollama, OpenAI-compatible, Anthropic, …) for the CLI.

Routing stays deterministic (``detect_intent``): intent routing is not what the
model is being trained or evaluated for, and keeping it fixed means the intent
rows of both reports are identical — any coverage delta is attributable purely
to build/edit proposal quality.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
from collections.abc import Callable

from ..agent.intent import detect_intent
from ..artifacts.metadata import TenantMetadata
from ..schemas.form_spec import AxisMember, FormSpecification, MemberSelection

# complete(system_prompt, user_message) -> raw model text (synchronous).
CompleteFn = Callable[[str, str], str]

_SELECTION_TYPES = (
    "member, memberList, range, relativeRange, children, inclusiveChildren, "
    "descendants, inclusiveDescendants, levelZeroDescendants, ancestors, "
    "inclusiveAncestors, siblings, substitutionVariable, userVariable, "
    "attribute, namedSelection"
)

_BUILD_INSTRUCTIONS = f"""You translate a planner's natural-language request into a FormSpecification.

Output rules — follow them exactly:
- Respond with a single JSON object and NOTHING else: no prose, no markdown fences.
- Keys are camelCase and must match the FormSpecification schema shown in the examples
  (name, application, cube, pov, pages, rows, columns, display, ...). Unknown keys are rejected.
- Every axis entry is {{"dimension": ..., "selection": {{"type": ..., ...}}}}.
- selection.type must be one of: {_SELECTION_TYPES}.
- Use only cubes, dimensions, members and variables that appear in the metadata above.
- rows and columns must each contain at least one dimension; a dimension may appear
  on exactly one axis (pov, pages, rows or columns)."""

_EDIT_INSTRUCTIONS = """You apply a conversational edit to an existing FormSpecification.

Output rules — follow them exactly:
- Respond with the COMPLETE edited FormSpecification as a single JSON object and
  NOTHING else: no prose, no markdown fences.
- Keep every part of the specification that the instruction does not mention unchanged.
- If the instruction is already satisfied, return the specification unchanged.
- Use only dimensions, members and variables that appear in the metadata above."""


# --- prompt building -------------------------------------------------------

def metadata_summary(md: TenantMetadata, members_per_dim: int = 8) -> str:
    """Compact, capped text summary of the tenant metadata for the system prompt.

    Only a few members per dimension are shown — enough to ground names like
    ``Total Payroll`` without ballooning the prompt on a large outline.
    """
    lines = [f"Application: {md.application}", "Cubes:"]
    for cube in md.cubes.values():
        lines.append(f"  - {cube.name}: dimensions [{', '.join(cube.dimensions)}]")
    lines.append("Dimensions (sample members):")
    for dim in md.dimensions:
        order = md.member_order.get(dim, [])
        sample = ", ".join(order[:members_per_dim])
        more = "" if len(order) <= members_per_dim else f", … ({len(order)} members total)"
        lines.append(f"  - {dim}: {sample}{more}")
    if md.variables:
        names = ", ".join(sorted(v.name for v in md.variables.values()))
        lines.append(f"Substitution/user variables: {names}")
    return "\n".join(lines)


def _dump(spec: FormSpecification) -> str:
    return json.dumps(spec.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False)


def _mcw_spec(
    name: str,
    cube: str,
    scenario: str,
    row_dim: str,
    row_type: str,
    row_member: str,
    page_entity: str | None = None,
) -> FormSpecification:
    """A canonical MCWPCF form shaped like the deterministic builder's output."""
    page_sel = (
        MemberSelection(type="member", member=page_entity)
        if page_entity
        else MemberSelection(type="userVariable", variable="CurrentEntity")
    )
    return FormSpecification(
        name=name,
        application="MCWPCF",
        cube=cube,
        pov=[
            AxisMember(dimension="Scenario", selection=MemberSelection(type="member", member=scenario)),
            AxisMember(dimension="Version", selection=MemberSelection(type="member", member="Working")),
        ],
        pages=[AxisMember(dimension="Entity", selection=page_sel)],
        rows=[AxisMember(dimension=row_dim,
                         selection=MemberSelection(type=row_type, member=row_member),
                         suppress_missing=True)],
        columns=[AxisMember(dimension="Period", selection=MemberSelection(type="range", start="Jan", end="Dec"))],
    )


# Built-in example bank, grounded in the MCWPCF fixtures and shaped like the
# corpus build cases. Constructed through the schema so every example is valid.
BUILD_EXAMPLES: list[tuple[str, FormSpecification]] = [
    ("Create an Actuals form with level-zero descendants of Total Payroll in rows",
     _mcw_spec("Actual Payroll Form", "OEP_WFP", "Actual", "Account", "levelZeroDescendants", "Total Payroll")),
    ("Build a budget revenue form",
     _mcw_spec("Budget Revenue Form", "OEP_FS", "Budget", "Account", "children", "Total Revenue")),
    ("Create a forecast form with children of Total Revenue in rows",
     _mcw_spec("Forecast Revenue Form", "OEP_FS", "Forecast", "Account", "children", "Total Revenue")),
    ("new cash form with children of Total Account in rows",
     _mcw_spec("Actual Cash Form", "OEP_DCSH", "Actual", "Account", "children", "Total Account")),
    ("create a headcount form with descendants of Total Employees in rows",
     _mcw_spec("Actual Workforce Form", "OEP_WFP", "Actual", "Employee", "descendants", "Total Employees")),
    ("budget form for the EMEA entity with children of Total Revenue in rows",
     _mcw_spec("Budget Revenue Form", "OEP_FS", "Budget", "Account", "children", "Total Revenue",
               page_entity="EMEA")),
]


def _edit_examples() -> list[tuple[FormSpecification, str, FormSpecification]]:
    """(before, instruction, after) triples for the edit prompt."""
    base = BUILD_EXAMPLES[0][1]
    read_only = base.model_copy(deep=True)
    read_only.display.read_only = True
    hidden = base.model_copy(deep=True)
    hidden.display.hidden_members = ["Mar", "Apr"]
    return [
        (base, "make the form read-only", read_only),
        (base, "hide March and April", hidden),
    ]


EDIT_EXAMPLES: list[tuple[FormSpecification, str, FormSpecification]] = _edit_examples()


# --- response parsing ------------------------------------------------------

def extract_json(text: str) -> dict:
    """Return the first JSON object embedded in ``text``.

    Tolerates markdown fences and surrounding prose by scanning for the first
    balanced ``{...}`` (string-aware, so braces inside values don't confuse it).
    Raises ``ValueError`` when no parsable object exists — the runner records
    that as an errored case.
    """
    start = text.find("{")
    while start != -1:
        depth, in_str, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if escaped:
                escaped = False
                continue
            if in_str:
                if ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break  # not valid JSON — try the next opening brace
                    if isinstance(obj, dict):
                        return obj
                    break
        start = text.find("{", start + 1)
    raise ValueError("model response contains no JSON object")


# --- the strategy ----------------------------------------------------------

class LlmStrategy:
    """LLM-proposes / deterministic-validates NLU, pluggable into ``run_eval``.

    ``complete`` is any synchronous ``(system, user) -> text`` function; use
    :func:`provider_complete` for a real provider or a plain lambda in tests.
    """

    def __init__(self, complete: CompleteFn, few_shot: int = 4, name: str = "llm") -> None:
        self.complete = complete
        self.few_shot = few_shot
        self.name = name

    # Routing is deliberately deterministic — see the module docstring.
    def route(self, utterance: str) -> str:
        return detect_intent(utterance).skill

    def build(self, utterance: str, md: TenantMetadata, application: str) -> FormSpecification:
        raw = self.complete(self.build_system_prompt(md, application), utterance)
        return FormSpecification.model_validate(extract_json(raw))

    def edit(self, spec: FormSpecification, utterance: str, md: TenantMetadata) -> bool:
        """Protocol-compatible edit: apply the proposal in place, return changed."""
        new_spec, changed, _changes = self.propose_edit(spec, utterance, md)
        for field in type(spec).model_fields:
            setattr(spec, field, getattr(new_spec, field))
        return changed

    def propose_edit(
        self, spec: FormSpecification, utterance: str, md: TenantMetadata
    ) -> tuple[FormSpecification, bool, list[str]]:
        """current spec JSON + instruction → (new_spec, changed, changes)."""
        user = (
            f"Current specification:\n{_dump(spec)}\n\n"
            f"Edit instruction: {utterance}\n\n"
            "Respond with the complete edited FormSpecification JSON."
        )
        raw = self.complete(self.edit_system_prompt(md), user)
        new_spec = FormSpecification.model_validate(extract_json(raw))
        before = spec.model_dump(by_alias=True)
        after = new_spec.model_dump(by_alias=True)
        changes = [f"{field} updated" for field in before if before[field] != after[field]]
        return new_spec, before != after, changes

    # --- prompts ---
    def build_system_prompt(self, md: TenantMetadata, application: str) -> str:
        parts = [
            "You are the EPM Wizard form designer for the "
            f"'{application}' application.",
            "",
            metadata_summary(md),
            "",
            _BUILD_INSTRUCTIONS,
            "",
        ]
        for i, (utterance, spec) in enumerate(BUILD_EXAMPLES[: self.few_shot], start=1):
            parts += [f"### Example {i}", f"Request: {utterance}", "Response:", _dump(spec), ""]
        return "\n".join(parts)

    def edit_system_prompt(self, md: TenantMetadata) -> str:
        parts = [
            "You are the EPM Wizard form editor.",
            "",
            metadata_summary(md),
            "",
            _EDIT_INSTRUCTIONS,
            "",
        ]
        for i, (before, instruction, after) in enumerate(EDIT_EXAMPLES[: self.few_shot], start=1):
            parts += [
                f"### Example {i}",
                f"Current specification: {_dump(before)}",
                f"Instruction: {instruction}",
                "Response:",
                _dump(after),
                "",
            ]
        return "\n".join(parts)


# --- provider plumbing -----------------------------------------------------

def _run_sync(coro):
    """Run a coroutine to completion from sync code, inside or outside a loop.

    ``run_eval`` is async, so strategy code executes inside a running event
    loop; a bare ``asyncio.run`` would raise there. Fall back to a fresh loop
    on a worker thread in that case.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def provider_complete(
    provider_type: str,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> CompleteFn:
    """A ``complete`` function backed by a real :class:`AIProvider`.

    The provider class comes from the registry's mapping, so every registered
    provider type (ollama, openai, generic, anthropic, gemini, mock, …)
    works. The API key is the explicit argument if given, else the standard env
    vars the registry already knows for that provider type.
    """
    from ..ai.base import AIMessage, ProviderConfig
    from ..ai.registry import _ENV_KEYS, _class_for

    key = api_key
    if key is None:
        for env_name in _ENV_KEYS.get(provider_type, []):
            if os.environ.get(env_name):
                key = os.environ[env_name]
                break

    config = ProviderConfig(
        provider_type=provider_type, base_url=base_url, api_key=key, default_model=model,
    )
    provider = _class_for(provider_type)(config)

    def complete(system: str, user: str) -> str:
        return _run_sync(provider.complete(
            [AIMessage(role="user", content=user)],
            system=system, model=model, temperature=0.0, max_tokens=2048,
        ))

    return complete
