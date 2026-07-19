"""LlmStrategy: the parse → validate → score pipeline, with no network ever.

The ``complete`` function is injected, so these tests drive the full harness
with fakes: an oracle fake (returns golden JSON) proves a good model scores
high end to end; malformed-output fakes prove bad responses are counted as
errored cases rather than crashing the run; prompt tests pin the metadata
summary and few-shot contract the real providers will receive.
"""

from __future__ import annotations

import re

import pytest

from app.agent.form_nlu import apply_edit, build_initial_spec
from app.eval.llm_strategy import (
    BUILD_EXAMPLES,
    EDIT_EXAMPLES,
    LlmStrategy,
    extract_json,
    provider_complete,
)
from app.eval.runner import run_eval
from app.schemas.form_spec import FormSpecification

APPLICATION = "MCWPCF"


def _json_of(spec: FormSpecification) -> str:
    return spec.model_dump_json(by_alias=True, exclude_none=True)


def _oracle_complete(md):
    """A fake model that always proposes the deterministic parser's golden spec,
    wrapped in prose + markdown fences (the messy-but-correct response shape)."""

    def complete(system: str, user: str) -> str:
        if "Edit instruction:" in user:
            spec = FormSpecification.model_validate(extract_json(user))
            instruction = re.search(r"Edit instruction: (.*)", user).group(1)
            apply_edit(spec, instruction, md)
            return f"Sure — here is the updated form:\n```json\n{_json_of(spec)}\n```"
        spec, _inferences, _questions = build_initial_spec(user, md, APPLICATION)
        return f"Here is the form you asked for:\n```json\n{_json_of(spec)}\n```\nLet me know!"

    return complete


# --- end-to-end: golden responses score high -------------------------------

async def test_oracle_fake_scores_high_end_to_end(md):
    """With correct golden JSON coming back, the LLM strategy must match the
    deterministic baseline's floors on the identical corpus — proving parse,
    validate and score all work through the LLM path."""
    report = await run_eval(LlmStrategy(_oracle_complete(md)))
    assert report.strategy == "llm"
    assert not report.errored, [f"{c.id}: {c.error}" for c in report.errored]
    assert report.coverage >= 0.80
    assert report.build_coverage >= 0.80
    assert report.edit_coverage >= 0.85
    assert report.by_tag().get("supported", 0.0) >= 0.98


async def test_route_is_deterministic(md):
    """Routing never consults the model — a crashing fake must not be called."""

    def explode(system: str, user: str) -> str:
        raise AssertionError("route() must not call the model")

    assert LlmStrategy(explode).route("Create an Actuals form") == "forms"


# --- failure modes: errored, never crashed ---------------------------------

async def test_prose_response_counts_as_error_not_crash(md):
    report = await run_eval(LlmStrategy(lambda s, u: "Sorry, I cannot produce JSON."))
    build_and_edit = [c for c in report.cases if c.kind in ("build", "edit")]
    assert build_and_edit and all(c.error for c in build_and_edit)
    # intent routing stays deterministic and unaffected
    assert report.intent_coverage >= 0.80


async def test_off_schema_json_counts_as_error(md):
    """Parsable JSON that fails FormSpecification validation is a real failure."""
    report = await run_eval(LlmStrategy(lambda s, u: '{"name": "X", "bogus": true}'))
    build = [c for c in report.cases if c.kind == "build"]
    assert build and all(c.error and "ValidationError" in c.error for c in build)


def test_build_raises_on_malformed_response(md):
    strategy = LlmStrategy(lambda s, u: "no json here")
    with pytest.raises(ValueError):
        strategy.build("Create an Actuals form", md, APPLICATION)


# --- JSON extraction -------------------------------------------------------

def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_prose_wrapped():
    text = 'Here you go:\n```json\n{"a": {"b": 2}}\n```\nAnything else?'
    assert extract_json(text) == {"a": {"b": 2}}


def test_extract_json_braces_inside_strings():
    assert extract_json('answer: {"a": "curly } brace {", "b": "\\"q\\""} end') == {
        "a": "curly } brace {", "b": '"q"',
    }


def test_extract_json_skips_invalid_then_finds_object():
    assert extract_json("{not json} but then {\"a\": 1}") == {"a": 1}


def test_extract_json_no_object_raises():
    with pytest.raises(ValueError):
        extract_json("I have no JSON for you.")


# --- build path ------------------------------------------------------------

async def test_build_parses_fenced_response_into_spec(md):
    golden = BUILD_EXAMPLES[0][1]
    strategy = LlmStrategy(lambda s, u: f"Of course.\n```json\n{_json_of(golden)}\n```")
    spec = strategy.build("Create an Actuals payroll form", md, APPLICATION)
    assert isinstance(spec, FormSpecification)
    assert spec.cube == "OEP_WFP"
    assert spec.rows[0].selection.type == "levelZeroDescendants"
    assert spec.rows[0].selection.member == "Total Payroll"


# --- edit path -------------------------------------------------------------

async def test_edit_applies_proposal_in_place(md):
    base, _instruction, edited = EDIT_EXAMPLES[0]
    spec = base.model_copy(deep=True)
    strategy = LlmStrategy(lambda s, u: _json_of(edited))
    changed = strategy.edit(spec, "make the form read-only", md)
    assert changed is True
    assert spec.display.read_only is True  # mutated in place, as the runner scores it


async def test_edit_unchanged_spec_reports_not_changed(md):
    base = EDIT_EXAMPLES[0][0]
    spec = base.model_copy(deep=True)
    strategy = LlmStrategy(lambda s, u: _json_of(base))
    assert strategy.edit(spec, "use aliases", md) is False


async def test_propose_edit_returns_new_spec_changed_and_changes(md):
    base, _instruction, edited = EDIT_EXAMPLES[1]
    strategy = LlmStrategy(lambda s, u: _json_of(edited))
    new_spec, changed, changes = strategy.propose_edit(
        base.model_copy(deep=True), "hide March and April", md)
    assert changed is True
    assert new_spec.display.hidden_members == ["Mar", "Apr"]
    assert changes == ["display updated"]


# --- prompt contract -------------------------------------------------------

async def test_build_prompt_contains_metadata_and_n_examples(md):
    captured: dict[str, str] = {}

    def fake(system: str, user: str) -> str:
        captured["system"], captured["user"] = system, user
        return _json_of(BUILD_EXAMPLES[0][1])

    LlmStrategy(fake, few_shot=3).build("Create an Actuals form", md, APPLICATION)

    system = captured["system"]
    # metadata summary: cubes, dimensions and sample members from the real tenant
    for cube in ("OEP_WFP", "OEP_FS", "OEP_DCSH"):
        assert cube in system
    for dim in ("Account", "Scenario", "Period", "Employee"):
        assert f"- {dim}:" in system
    assert "Actual" in system and "Forecast" in system  # Scenario sample members
    assert "CurrYr" in system  # substitution variables
    # exactly N few-shot examples, each with request + JSON response
    assert system.count("### Example") == 3
    assert system.count("Request:") == 3
    # the utterance travels as the user message, not baked into the system prompt
    assert captured["user"] == "Create an Actuals form"


async def test_few_shot_is_capped_by_example_bank(md):
    strategy = LlmStrategy(lambda s, u: _json_of(BUILD_EXAMPLES[0][1]), few_shot=99)
    system = strategy.build_system_prompt(md, APPLICATION)
    assert system.count("### Example") == len(BUILD_EXAMPLES)


async def test_edit_prompt_contains_metadata_examples_and_current_spec(md):
    base = EDIT_EXAMPLES[0][0]
    captured: dict[str, str] = {}

    def fake(system: str, user: str) -> str:
        captured["system"], captured["user"] = system, user
        return _json_of(base)

    LlmStrategy(fake, few_shot=2).edit(base.model_copy(deep=True), "hide March", md)
    assert "OEP_WFP" in captured["system"]
    assert captured["system"].count("### Example") == 2
    assert "Current specification:" in captured["user"]
    assert "Edit instruction: hide March" in captured["user"]


def test_example_bank_specs_are_schema_valid():
    """Every few-shot example must round-trip through the schema it teaches."""
    for _utterance, spec in BUILD_EXAMPLES:
        FormSpecification.model_validate(extract_json(_json_of(spec)))
    for before, _instruction, after in EDIT_EXAMPLES:
        FormSpecification.model_validate(extract_json(_json_of(before)))
        FormSpecification.model_validate(extract_json(_json_of(after)))


# --- provider plumbing (mock provider — still no network) ------------------

async def test_provider_complete_works_inside_running_event_loop():
    """provider_complete + the registry's mock provider, called from async code
    (exactly how run_eval invokes it) — exercises the worker-thread fallback."""
    complete = provider_complete("mock")
    out = complete("COMPOSE: {\"ok\": true}", "hello")
    assert extract_json(out) == {"ok": True}


def test_provider_complete_works_without_event_loop():
    complete = provider_complete("mock")
    out = complete("COMPOSE: pong", "ping")
    assert out.strip() == "pong"
