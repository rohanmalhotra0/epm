"""Generated artifacts must resolve against the tenant's *own* outline.

The bundled MCW fixtures use the Planning-standard names (Account, Actual,
Working, Jan:Dec, CurrentEntity), which is exactly what let the old hardcoded
defaults pass every test while failing on a real EPBCS application. The
metadata here deliberately uses none of them: the account dimension is called
"Line Item", every seeded member carries the OEP_ prefix, and there is no
CurrentEntity user variable.
"""

from __future__ import annotations

import pytest

from app.agent import outline_defaults as od
from app.agent.form_nlu import apply_edit, build_initial_spec
from app.agent.report_nlu import build_initial_report
from app.artifacts import validate_form
from app.artifacts.metadata import build_metadata
from app.artifacts.preview import build_preview
from app.schemas.context import CubeRecord, DimensionRecord, MemberRecord, VariableRecord

APP = "MCW_PCF"
CUBE = "CFREP"
CUBE_DIMS = ["Scenario", "Version", "Line Item", "Years", "Currency", "Entity", "Period"]
DIM_TYPES = {"Line Item": "account", "Period": "period", "Years": "years",
             "Scenario": "scenario", "Version": "version", "Entity": "entity",
             "Currency": "currency"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _members() -> list[MemberRecord]:
    out: list[MemberRecord] = []

    def m(dim, name, parent=None, children=()):
        # `level` is left None on purpose — connectors don't always populate it.
        out.append(MemberRecord(name=name, dimension=dim, application=APP,
                                parent=parent, children=list(children)))

    m("Period", "YearTotal", children=["Q1", "Q2", "Q3", "Q4"])
    m("Period", "BegBalance")
    for i, q in enumerate(["Q1", "Q2", "Q3", "Q4"]):
        kids = MONTHS[i * 3:i * 3 + 3]
        m("Period", q, "YearTotal", kids)
        for mo in kids:
            m("Period", mo, q)

    m("Scenario", "Scenario", children=["OEP_Actual", "OEP_Plan", "OEP_Forecast"])
    for s in ["OEP_Actual", "OEP_Plan", "OEP_Forecast"]:
        m("Scenario", s, "Scenario")
    # decoys that contain "Actual" as a substring but are not the Actual scenario
    m("Scenario", "OEP_Reporting Actual Range", "Scenario")
    m("Scenario", "OEP_Reporting Actual vs Forecast Range", "Scenario")

    m("Version", "Version", children=["OEP_Working", "OEP_Final"])
    m("Version", "OEP_Working", "Version")
    m("Version", "OEP_Final", "Version")

    m("Line Item", "Total Line Item", children=["Cash Receipts", "Cash Disbursements"])
    m("Line Item", "Cash Receipts", "Total Line Item", ["Customer Collections"])
    m("Line Item", "Customer Collections", "Cash Receipts")
    m("Line Item", "Cash Disbursements", "Total Line Item", ["SOFR Loan Interest"])
    m("Line Item", "SOFR Loan Interest", "Cash Disbursements")

    m("Entity", "Total Entity", children=["US Operations"])
    m("Entity", "US Operations", "Total Entity")
    m("Years", "All Years", children=["FY26"])
    m("Years", "FY26", "All Years")
    m("Currency", "Currency", children=["USD"])
    m("Currency", "USD", "Currency")
    return out


@pytest.fixture
def md():
    dims = [DimensionRecord(name=d, application=APP, type=DIM_TYPES[d], cubes=[CUBE])
            for d in CUBE_DIMS]
    cubes = [CubeRecord(name=CUBE, application=APP, dimensions=CUBE_DIMS)]
    # No CurrentEntity user variable — the Planning convention is not universal.
    variables = [VariableRecord(name="OEP_CurYr", application=APP, scope="substitution",
                                dimension="Years", value="FY26")]
    return build_metadata(APP, cubes, dims, _members(), variables)


def test_dimension_located_by_type_not_name(md):
    assert od.find_dimension(md, "account", cube=CUBE) == "Line Item"
    assert od.find_dimension(md, "period", cube=CUBE) == "Period"
    assert od.find_dimension(md, "nonexistent-type", cube=CUBE) is None


def test_vendor_prefixed_members_resolve(md):
    assert od.resolve_member(md, "Scenario", "Actual") == "OEP_Actual"
    assert od.resolve_member(md, "Version", "Working") == "OEP_Working"
    # a spec written against the prefixed name still resolves on an unprefixed app
    assert od.resolve_member(md, "Scenario", "OEP_Forecast") == "OEP_Forecast"
    assert od.resolve_member(md, "Scenario", "Nonsense") is None


def test_prefix_match_prefers_the_scenario_over_longer_ranges(md):
    """"Actual" must not match "OEP_Reporting Actual vs Forecast Range"."""
    assert od.resolve_member(md, "Scenario", "Actual") == "OEP_Actual"


def test_generated_form_is_valid_and_complete(md):
    spec, _inferences, questions = build_initial_spec("generate a form for the actuals", md, APP)
    report = validate_form(spec, md)
    assert report.valid, [i.message for i in report.issues if i.severity == "error"]
    assert not questions
    # every cube dimension is pinned — nothing left to the renderer's default
    assert set(spec.dimensions_used()) == set(CUBE_DIMS)
    pov = {am.dimension: am.selection for am in spec.pov}
    assert pov["Scenario"].member == "OEP_Actual"
    assert pov["Version"].member == "OEP_Working"
    assert spec.rows[0].dimension == "Line Item"


def test_pages_fall_back_when_no_user_variable_exists(md):
    """{CurrentEntity} is only valid if the tenant actually declares it."""
    spec, *_ = build_initial_spec("generate a form for the actuals", md, APP)
    entity = next(am for am in spec.pages if am.dimension == "Entity")
    assert entity.selection.type != "userVariable"
    assert entity.selection.member == "Total Entity"


def test_period_range_excludes_quarter_headers(md):
    """Jan:Dec is 12 months even when the outline carries no level numbers."""
    spec, *_ = build_initial_spec("generate a form for the actuals", md, APP)
    preview = build_preview(spec, md)
    columns = next(a for a in preview.columns if a.dimension == "Period")
    assert columns.resolved_count == 12


def test_unknown_scenario_asks_instead_of_substituting(md):
    """Asking for a scenario the app lacks must not silently fall back to Actual."""
    spec, _inferences, questions = build_initial_spec("create a budget form", md, APP)
    assert any("Budget" in q for q in questions)
    scenario = next(am for am in spec.pov if am.dimension == "Scenario")
    assert scenario.selection.member == "OEP_Actual"  # skeleton default, flagged above


def test_edits_resolve_against_the_outline(md):
    spec, *_ = build_initial_spec("generate a form for the actuals", md, APP)
    changed, changes, _ = apply_edit(spec, "change the scenario to forecast", md)
    assert changed and any("OEP_Forecast" in c for c in changes)
    assert validate_form(spec, md).valid

    changed, changes, _ = apply_edit(spec, "use level-zero descendants instead of children", md)
    assert changed and any("Line Item rows" in c for c in changes)
    assert validate_form(spec, md).valid


def test_unmatched_reference_form_is_called_out(md):
    """"like the SOFR loan" must not silently yield a generic form."""
    spec, _inferences, questions = build_initial_spec(
        "Generate a form like the SOFR loan but fully working", md, APP)
    assert any("SOFR loan" in q for q in questions)
    # ...and what it does build is still valid
    assert validate_form(spec, md).valid


def test_generated_report_resolves(md):
    spec, _inferences, questions = build_initial_report("cash report by month", md, APP)
    grid = spec.grids[0]
    assert not questions
    assert {am.dimension for am in grid.pov} == {"Scenario", "Version"}
    assert next(am for am in grid.pov if am.dimension == "Version").selection.member == "OEP_Working"
    assert grid.rows[0].dimension == "Line Item"
    assert grid.columns[0].dimension == "Period"
