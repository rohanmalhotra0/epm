"""Golden NLU corpus, grounded in the demo tenant (``MCWPCF``).

Cases are deliberately a mix of two kinds:

* ``supported`` — phrasings the deterministic parser is expected to handle. These
  keep the baseline honest and guard against regressions.
* ``paraphrase`` — natural rewordings a good NLU *should* handle but the current
  regex parser does not (cross-dimension members, "just the leaf accounts",
  multi-member edits, verb synonyms). Their expectations describe the **correct**
  answer, so they score partial today and will climb as the NLU improves — this
  is where the coverage headroom lives.

Add cases freely; the harness scores whatever is here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .scorer import AxisExpect, Expect


@dataclass
class BuildCase:
    id: str
    utterance: str
    expect: Expect
    tags: tuple[str, ...] = ()


@dataclass
class EditCase:
    id: str
    base: str  # utterance used to build the starting spec
    edit: str  # the conversational edit under test
    expect: Expect
    expect_changed: bool = True
    tags: tuple[str, ...] = ()


@dataclass
class IntentCase:
    utterance: str
    skill: str
    tags: tuple[str, ...] = ()


# --- intent routing --------------------------------------------------------

INTENT_CASES: list[IntentCase] = [
    IntentCase("Create an Actuals form", "forms", ("supported",)),
    IntentCase("make a workforce planning form", "forms", ("supported",)),
    IntentCase("build a form for headcount", "forms", ("supported",)),
    IntentCase("/forms make it read-only", "forms", ("supported", "slash")),
    IntentCase("run the IR rule", "rules", ("supported",)),
    IntentCase("run Aggregate Financials", "rules", ("paraphrase",)),  # bare rule name, no "the"/"rule"
    IntentCase("explain the IR rule", "rules", ("supported",)),
    IntentCase("generate a report of revenue by entity", "reports", ("supported",)),
    IntentCase("what cubes and dimensions exist?", "search", ("supported",)),
    IntentCase("what rules can I run", "search", ("supported",)),
    IntentCase("visualize OEP_DCSH", "architecture", ("supported",)),
    IntentCase("what dimensions are in OEP_WFP", "architecture", ("supported",)),
    IntentCase("compare OEP_FS and OEP_WFP", "compare", ("supported",)),
    IntentCase("build the context for this application", "context", ("supported",)),
    IntentCase("deploy", "deploy", ("supported",)),
    IntentCase("roll back the last deployment", "rollback", ("supported",)),
    IntentCase("help", "help", ("supported",)),
    IntentCase("uploadFile data.csv", "epmAutomate", ("supported",)),
    # --- headroom: natural phrasings the keyword router misses today ---
    IntentCase("walk me through the IR rule", "explain", ("paraphrase",)),
    IntentCase("I need to get this form out to production", "deploy", ("paraphrase",)),
]


# --- form building ---------------------------------------------------------

BUILD_CASES: list[BuildCase] = [
    BuildCase(
        "build.payroll_l0",
        "Create an Actuals form with level-zero descendants of Total Payroll in rows",
        Expect(
            cube="OEP_WFP",
            rows=[AxisExpect("Account", type="levelZeroDescendants", member="Total Payroll")],
            pov={"Scenario": "Actual"},
            valid=True,
        ),
        ("supported",),
    ),
    BuildCase(
        "build.budget_revenue",
        "Build a budget revenue form",
        Expect(cube="OEP_FS", pov={"Scenario": "Budget"}, valid=True),
        ("supported",),
    ),
    BuildCase(
        "build.forecast_children",
        "Create a forecast form with children of Total Revenue in rows",
        Expect(
            cube="OEP_FS",
            rows=[AxisExpect("Account", type="children", member="Total Revenue")],
            pov={"Scenario": "Forecast"},
            valid=True,
        ),
        ("supported",),
    ),
    BuildCase(
        "build.cash_children",
        "new cash form with children of Total Account in rows",
        Expect(
            cube="OEP_DCSH",
            rows=[AxisExpect("Account", type="children", member="Total Account")],
            valid=True,
        ),
        ("supported",),
    ),
    BuildCase(
        "build.scenario_not_from_reference",
        "Create a forecast form based on Actual Revenue Review",
        # The scenario is Forecast (the user's word), not Actual (from the ref form name).
        Expect(pov={"Scenario": "Forecast"}, valid=True),
        ("supported",),
    ),
    BuildCase(
        "build.workforce_descendants",
        "make a workforce form with descendants of Total Payroll in rows",
        Expect(
            cube="OEP_WFP",
            rows=[AxisExpect("Account", type="descendants", member="Total Payroll")],
            valid=True,
        ),
        ("supported",),
    ),
    # --- headroom: correct answer described; parser falls back today ---
    BuildCase(
        "build.leaf_paraphrase",
        "make me a form showing just the leaf accounts under Total Payroll",
        Expect(
            cube="OEP_WFP",
            rows=[AxisExpect("Account", type="levelZeroDescendants", member="Total Payroll")],
            valid=True,
        ),
        ("paraphrase",),
    ),
    BuildCase(
        "build.cross_dimension_member",
        "create a headcount form with descendants of Total Employees in rows",
        Expect(
            cube="OEP_WFP",
            rows=[AxisExpect("Employee", type="descendants", member="Total Employees")],
            valid=True,
        ),
        ("supported",),  # fixed: row members resolve across all dimensions
    ),
    BuildCase(
        "build.entity_scoped",
        "budget form for the EMEA entity with children of Total Revenue in rows",
        Expect(
            cube="OEP_FS",
            rows=[AxisExpect("Account", type="children", member="Total Revenue")],
            pov={"Scenario": "Budget"},
            pages={"Entity": "EMEA"},
            valid=True,
        ),
        ("paraphrase",),
    ),
]


# --- conversational edits --------------------------------------------------

_BASE = "Create an Actuals form"

EDIT_CASES: list[EditCase] = [
    EditCase("edit.move_pov", _BASE, "move Entity to POV",
             Expect(pov={"Entity": "CurrentEntity"}), tags=("supported",)),
    EditCase("edit.hide_month", _BASE, "hide March",
             Expect(hidden_members=["Mar"]), tags=("supported",)),
    EditCase("edit.aliases", _BASE, "use aliases",
             Expect(use_aliases=True), expect_changed=False, tags=("supported",)),
    EditCase("edit.technical_names", _BASE, "show technical names instead of aliases",
             Expect(use_aliases=False), tags=("supported",)),
    EditCase("edit.readonly", _BASE, "make the form read-only",
             Expect(read_only=True), tags=("supported",)),
    EditCase("edit.readonly_and_hide", _BASE, "make it read-only and hide the first column",
             Expect(read_only=True, hidden_members=["Jan"]), tags=("supported",)),
    EditCase("edit.attach_rule", _BASE, "attach the IR rule",
             Expect(rules=["IR"]), tags=("supported",)),
    EditCase("edit.change_scenario", _BASE, "change scenario to Forecast",
             Expect(pov={"Scenario": "Forecast"}), tags=("supported",)),
    EditCase("edit.limit_rows", _BASE, "only show 5 rows",
             Expect(rows=[AxisExpect("Account", type="memberList")]), tags=("supported",)),
    EditCase("edit.change_selection", _BASE, "use level-zero descendants",
             Expect(rows=[AxisExpect("Account", type="levelZeroDescendants")]), tags=("supported",)),
    EditCase("edit.hide_account", _BASE, "hide the Bonus account",
             Expect(hidden_members=["Bonus"]), tags=("supported",)),
    # --- headroom ---
    EditCase("edit.hide_two_months", _BASE, "hide March and April",
             Expect(hidden_members=["Mar", "Apr"]), tags=("supported",)),  # fixed: multi-member hide
    EditCase("edit.switch_scenario_synonym", _BASE, "switch to forecast",
             Expect(pov={"Scenario": "Forecast"}), tags=("paraphrase",)),
]


def all_tags() -> set[str]:
    tags: set[str] = set()
    for case in (*INTENT_CASES, *BUILD_CASES, *EDIT_CASES):
        tags.update(case.tags)
    return tags
