"""Deterministic form NLU tests (spec sections 22, 25)."""

from __future__ import annotations

import pytest

from app.agent.form_nlu import apply_edit, build_initial_spec
from app.agent.intent import detect_intent
from app.artifacts import build_metadata_from_connector, validate_form
from app.connector import DemoConnector



async def _md():
    return await build_metadata_from_connector(DemoConnector(), "MCWPCF")


@pytest.mark.parametrize("text,skill", [
    ("Create an Actuals form", "forms"),
    ("run the IR rule", "rules"),
    ("what cubes and dimensions exist?", "search"),
    ("visualize OEP_DCSH", "architecture"),
    ("explain the IR rule", "rules"),
    ("/forms make it read-only", "forms"),
    ("compare OEP_FS and OEP_WFP", "compare"),
    ("help", "help"),
])
def test_intent_routing(text, skill):
    assert detect_intent(text).skill == skill


async def test_build_initial_spec_infers_payroll_workforce():
    md = await _md()
    spec, inferences, _ = build_initial_spec(
        "Create an Actuals form with level-zero descendants of Total Payroll in rows", md, "MCWPCF")
    assert spec.cube == "OEP_WFP"
    assert spec.rows[0].selection.type == "levelZeroDescendants"
    assert spec.rows[0].selection.member == "Total Payroll"
    assert validate_form(spec, md).valid


async def test_edits_apply_correctly():
    md = await _md()
    spec, *_ = build_initial_spec("Create an Actuals form", md, "MCWPCF")
    changed, changes, _ = apply_edit(spec, "move Entity to POV", md)
    assert changed and any("Entity" in c for c in changes)
    assert any(a.dimension == "Entity" for a in spec.pov)

    apply_edit(spec, "hide March", md)
    assert "Mar" in spec.display.hidden_members

    apply_edit(spec, "make the form read-only", md)
    assert spec.display.read_only

    changed, changes, _ = apply_edit(spec, "attach the IR rule", md)
    assert any(a.rule_name == "IR" for a in spec.business_rule_associations)


async def test_ir_rule_match_is_not_a_substring_false_positive():
    from app.agent.form_nlu import _match_rule
    md = await _md()
    assert _match_rule(md, "IR") == "IR"  # not "Add New Hire" via 'h(ir)e'
