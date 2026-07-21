"""Deterministic rule validation tests (spec section 30) — symmetric to the
form validation coverage. Only spec-level, deterministic checks; the calc-script
FIX/ENDFIX check is a warning, never a compile-correctness claim."""

from __future__ import annotations

from app.agent import stream_turn
from app.ai import MockProvider
from app.artifacts.metadata import build_metadata_from_connector
from app.artifacts.rule_validation import validate_rule
from app.connector import DemoConnector
from app.schemas.rule_spec import (
    RuleSpecification,
    RuleType,
    RuntimePrompt,
    RuntimePromptType,
)
from app.services import conversations, projects


async def _md():
    return await build_metadata_from_connector(DemoConnector(), "MCWPCF")


def _spec(**overrides) -> RuleSpecification:
    base = dict(
        name="Copy Working to Final",
        type=RuleType.business_rule,
        application="MCWPCF",
        cube="OEP_FS",
        purpose="Promote working data to final",
        runtime_prompts=[
            RuntimePrompt(name="Entity", prompt_text="Select Entity",
                          type=RuntimePromptType.member, dimension="Entity"),
        ],
        referenced_dimensions=["Version"],
        referenced_variables=["CurrYr"],
    )
    base.update(overrides)
    return RuleSpecification(**base)


# --- unit checks ---------------------------------------------------------------


async def test_good_spec_is_valid():
    md = await _md()
    report = validate_rule(_spec(), md, script='FIX ("Working")\n  DATACOPY "Working" TO "Final";\nENDFIX')
    assert report.valid
    assert report.blocking is False
    assert report.errors == []


async def test_bad_cube_is_blocking_error():
    md = await _md()
    report = validate_rule(_spec(cube="NOPE"), md, script="/* body */")
    assert not report.valid and report.blocking
    codes = {i.code for i in report.errors}
    assert "CUBE_NOT_FOUND" in codes
    issue = next(i for i in report.issues if i.code == "CUBE_NOT_FOUND")
    assert "OEP_FS" in issue.candidates  # candidates are sorted(md.cubes)


async def test_unknown_runtime_prompt_dimension_is_error():
    md = await _md()
    spec = _spec(runtime_prompts=[RuntimePrompt(name="p", dimension="Widget",
                                                type=RuntimePromptType.member)])
    report = validate_rule(spec, md, script="/* body */")
    assert not report.valid and report.blocking
    issue = next(i for i in report.issues if i.code == "DIM_NOT_FOUND")
    assert issue.layer == "runtimePrompt"


async def test_empty_script_is_error():
    md = await _md()
    report = validate_rule(_spec(source=None), md, script="   ")
    assert not report.valid and report.blocking
    issue = next(i for i in report.issues if i.code == "EMPTY_SCRIPT")
    assert issue.layer == "script"


async def test_unbalanced_fix_endfix_is_warning_not_blocking():
    md = await _md()
    body = ('FIX ("Working")\n  DATACOPY "Working" TO "Final";\n'
            'FIX ("Actual")\n  CLEARBLOCK ALL;\nENDFIX')  # two FIX, one ENDFIX
    report = validate_rule(_spec(type=RuleType.calc_script), md, script=body)
    assert report.valid  # a warning does not invalidate
    assert report.blocking is False
    warn = next(i for i in report.warnings if i.code == "UNBALANCED_FIX")
    assert warn.layer == "script"


async def test_balanced_fix_endfix_has_no_warning():
    md = await _md()
    body = 'FIX ("Working")\n  DATACOPY "Working" TO "Final";\nENDFIX'
    report = validate_rule(_spec(type=RuleType.calc_script), md, script=body)
    assert not any(i.code == "UNBALANCED_FIX" for i in report.issues)


async def test_unknown_variable_is_error():
    md = await _md()
    report = validate_rule(_spec(referenced_variables=["NoSuchVar"]), md, script="/* body */")
    assert any(i.code == "VAR_NOT_FOUND" for i in report.errors)


async def test_unknown_member_is_warning_only():
    md = await _md()
    spec = _spec(referenced_dimensions=["Version"], referenced_members=["ZzzGhostMember"])
    report = validate_rule(spec, md, script="/* body */")
    assert report.valid  # member miss is best-effort -> warning, not blocking
    assert any(i.code == "MEMBER_NOT_FOUND" for i in report.warnings)


async def test_bad_name_is_error():
    md = await _md()
    report = validate_rule(_spec(name="bad;name"), md, script="/* body */")
    assert any(i.code == "BAD_NAME" for i in report.errors)


# --- e2e: the creation turn now emits a validationReport block -----------------


async def _turn(session, project, conv, text):
    conversations.add_message(session, conv.id, "user", text)
    events = []
    async for ev in stream_turn(session=session, project=project, conversation=conv,
                                connector=DemoConnector(), provider=MockProvider(),
                                application="MCWPCF", classification="development",
                                environment_name="MCW Demo (Local)", demo=True,
                                context_version_id=None, user_text=text):
        events.append(ev)
    return events


def _block_types(events):
    return [ev.data.get("type") for ev in events if str(ev.type) == "block"]


async def test_rule_creation_emits_validation_report(session):
    out = projects.create_project(session, "Rule Validation E2E Test")
    proj = projects.get_project(session, out.id)
    conv = conversations.create_conversation(session, proj.id)
    events = await _turn(session, proj, conv, "create a rule that copies working to final")
    types = _block_types(events)
    assert "rulePreview" in types
    assert "validationReport" in types
    assert types.index("rulePreview") < types.index("validationReport")
