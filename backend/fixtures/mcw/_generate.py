"""Deterministic generator for the MCWPCF demo tenant fixtures (spec section 42).

Run:  python fixtures/mcw/_generate.py   (from backend/)

Produces synthetic, clearly-labelled demo data — no real Oracle content. The
hierarchies and names are chosen so the spec's worked examples (Total Payroll,
Daily Cash Forecast, CurrentEntity, IR, Add New Hire) resolve end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

APP = "MCWPCF"
HERE = Path(__file__).resolve().parent

CUBES = [
    {"name": "OEP_FS", "application": APP, "type": "bso", "description": "Financials"},
    {"name": "OEP_WFP", "application": APP, "type": "bso", "description": "Workforce"},
    {"name": "OEP_DCSH", "application": APP, "type": "bso", "description": "Daily Cash"},
    {"name": "OEP_REP", "application": APP, "type": "aso", "description": "Reporting (aggregate)"},
]

FIN_CUBES = ["OEP_FS", "OEP_DCSH", "OEP_REP"]
ALL_FIN = ["OEP_FS", "OEP_WFP", "OEP_DCSH", "OEP_REP"]

DIMENSIONS = [
    {"name": "Account", "type": "account", "cubes": ALL_FIN, "dense": True},
    {"name": "Period", "type": "period", "cubes": ALL_FIN, "dense": True},
    {"name": "Years", "type": "years", "cubes": ALL_FIN, "dense": False},
    {"name": "Scenario", "type": "scenario", "cubes": ALL_FIN, "dense": False},
    {"name": "Version", "type": "version", "cubes": ALL_FIN, "dense": False},
    {"name": "Entity", "type": "entity", "cubes": ALL_FIN, "dense": False},
    {"name": "Currency", "type": "currency", "cubes": FIN_CUBES, "dense": False},
    {"name": "Employee", "type": "generic", "cubes": ["OEP_WFP"], "dense": False},
    {"name": "Job", "type": "generic", "cubes": ["OEP_WFP"], "dense": False},
    {"name": "BankAccount", "type": "generic", "cubes": ["OEP_DCSH"], "dense": False},
]

members: list[dict] = []


def add(name, dimension, parent=None, alias=None, storage="storeData", formula=None, data_type="currency"):
    members.append(
        {
            "name": name,
            "dimension": dimension,
            "application": APP,
            "alias": alias,
            "parent": parent,
            "children": [],
            "storage": storage,
            "formula": formula,
            "data_type": data_type,
        }
    )


def tree(dimension, node, parent=None):
    name = node["name"]
    add(
        name,
        dimension,
        parent=parent,
        alias=node.get("alias"),
        storage=node.get("storage", "storeData" if not node.get("children") else "storeData"),
        formula=node.get("formula"),
        data_type=node.get("data_type", "currency"),
    )
    for child in node.get("children", []):
        tree(dimension, child, parent=name)


# --- Account ---------------------------------------------------------------
tree("Account", {
    "name": "Total Account", "storage": "label", "children": [
        {"name": "Total Revenue", "alias": "Revenue", "children": [
            {"name": "Product Revenue", "alias": "Product Sales"},
            {"name": "Service Revenue", "alias": "Services"},
            {"name": "Other Revenue"},
        ]},
        {"name": "Total Expenses", "alias": "Operating Costs", "children": [
            {"name": "Total Payroll", "alias": "Total Payroll Costs", "children": [
                {"name": "Salaries", "alias": "Base Salaries"},
                {"name": "Wages", "alias": "Hourly Wages"},
                {"name": "Overtime"},
                {"name": "Bonus", "alias": "Bonuses"},
                {"name": "Commissions"},
                {"name": "Benefits", "alias": "Employee Benefits"},
                {"name": "Payroll Taxes", "alias": "Employer Taxes"},
            ]},
            {"name": "Total Operating Expenses", "alias": "OpEx", "children": [
                {"name": "Rent"},
                {"name": "Utilities"},
                {"name": "Marketing"},
                {"name": "Travel", "alias": "Travel & Entertainment"},
                {"name": "Depreciation"},
            ]},
        ]},
        {"name": "Net Income", "storage": "dynamicCalc",
         "formula": '"Total Revenue" - "Total Expenses";'},
    ],
})

# --- Period ----------------------------------------------------------------
tree("Period", {
    "name": "YearTotal", "storage": "label", "children": [
        {"name": "Q1", "storage": "dynamicCalc", "children": [
            {"name": "Jan", "alias": "January"}, {"name": "Feb", "alias": "February"}, {"name": "Mar", "alias": "March"}]},
        {"name": "Q2", "storage": "dynamicCalc", "children": [
            {"name": "Apr", "alias": "April"}, {"name": "May"}, {"name": "Jun", "alias": "June"}]},
        {"name": "Q3", "storage": "dynamicCalc", "children": [
            {"name": "Jul", "alias": "July"}, {"name": "Aug", "alias": "August"}, {"name": "Sep", "alias": "September"}]},
        {"name": "Q4", "storage": "dynamicCalc", "children": [
            {"name": "Oct", "alias": "October"}, {"name": "Nov", "alias": "November"}, {"name": "Dec", "alias": "December"}]},
    ],
})
add("BegBalance", "Period", parent=None, alias="Beginning Balance", data_type="currency")

# --- Years -----------------------------------------------------------------
tree("Years", {"name": "All Years", "storage": "label", "children": [
    {"name": "FY24"}, {"name": "FY25"}, {"name": "FY26"}, {"name": "FY27"},
]})

# --- Scenario / Version ----------------------------------------------------
tree("Scenario", {"name": "Scenario", "storage": "label", "children": [
    {"name": "Actual"}, {"name": "Budget"}, {"name": "Forecast"}, {"name": "Plan"},
]})
tree("Version", {"name": "Version", "storage": "label", "children": [
    {"name": "Working"}, {"name": "Final"},
]})

# --- Entity ----------------------------------------------------------------
tree("Entity", {"name": "Total Entity", "alias": "Total Company", "storage": "label", "children": [
    {"name": "US Operations", "alias": "United States", "children": [
        {"name": "US East"}, {"name": "US West"}]},
    {"name": "EMEA", "children": [
        {"name": "UK", "alias": "United Kingdom"}, {"name": "Germany"}, {"name": "France"}]},
    {"name": "APAC", "children": [
        {"name": "Japan"}, {"name": "Australia"}]},
]})

# --- Currency --------------------------------------------------------------
tree("Currency", {"name": "Currency", "storage": "label", "children": [
    {"name": "USD", "alias": "US Dollar"}, {"name": "EUR", "alias": "Euro"},
    {"name": "GBP", "alias": "British Pound"}, {"name": "JPY", "alias": "Japanese Yen"},
]})

# --- Workforce -------------------------------------------------------------
tree("Employee", {"name": "Total Employees", "storage": "label", "children": [
    {"name": "Existing Employees"}, {"name": "To Be Hired", "alias": "New Hires"},
]})
tree("Job", {"name": "Total Jobs", "storage": "label", "children": [
    {"name": "Engineer"}, {"name": "Manager"}, {"name": "Analyst"}, {"name": "Sales Rep"},
]})

# --- Bank ------------------------------------------------------------------
tree("BankAccount", {"name": "Total Banks", "storage": "label", "children": [
    {"name": "Operating Account"}, {"name": "Payroll Account"}, {"name": "Reserve Account"},
]})

# fill children arrays
by_key = {(m["dimension"], m["name"]): m for m in members}
for m in members:
    if m["parent"]:
        by_key[(m["dimension"], m["parent"])]["children"].append(m["name"])

# assign levels (0 = leaf)
def compute_level(m):
    if not m["children"]:
        return 0
    return 1 + max(compute_level(by_key[(m["dimension"], c)]) for c in m["children"])

for m in members:
    m["level"] = compute_level(m)

# --- Forms (normalised FormSpecification-compatible definitions) ------------
forms = [
    {
        "name": "Daily Cash Forecast", "application": APP, "cube": "OEP_DCSH",
        "folder": "Financials/Cash", "description": "Rolling daily cash forecast by bank account.",
        "definition": {
            "application": APP, "cube": "OEP_DCSH", "folder": "Financials/Cash",
            "pov": [
                {"dimension": "Scenario", "selection": {"type": "member", "member": "Forecast"}},
                {"dimension": "Version", "selection": {"type": "member", "member": "Working"}},
                {"dimension": "Currency", "selection": {"type": "member", "member": "USD"}},
                {"dimension": "Years", "selection": {"type": "member", "member": "FY26"}},
            ],
            "pages": [{"dimension": "Entity", "selection": {"type": "userVariable", "variable": "CurrentEntity"}}],
            "rows": [{"dimension": "BankAccount", "selection": {"type": "children", "member": "Total Banks"}, "suppressMissing": True}],
            "columns": [{"dimension": "Period", "selection": {"type": "range", "start": "Jan", "end": "Dec"}}],
            "display": {"useAliases": True, "suppressMissingRows": True},
        },
    },
    {
        "name": "Actual Revenue Review", "application": APP, "cube": "OEP_FS",
        "folder": "Financials/Actuals", "description": "Monthly actual revenue by entity.",
        "definition": {
            "application": APP, "cube": "OEP_FS", "folder": "Financials/Actuals",
            "pov": [
                {"dimension": "Scenario", "selection": {"type": "member", "member": "Actual"}},
                {"dimension": "Version", "selection": {"type": "member", "member": "Working"}},
                {"dimension": "Currency", "selection": {"type": "member", "member": "USD"}},
                {"dimension": "Years", "selection": {"type": "member", "member": "FY26"}},
            ],
            "pages": [{"dimension": "Entity", "selection": {"type": "userVariable", "variable": "CurrentEntity"}}],
            "rows": [{"dimension": "Account", "selection": {"type": "children", "member": "Total Revenue"}, "suppressMissing": True}],
            "columns": [{"dimension": "Period", "selection": {"type": "range", "start": "Jan", "end": "Dec"}}],
            "display": {"useAliases": True, "suppressMissingRows": True},
        },
    },
    {
        "name": "Workforce Planning", "application": APP, "cube": "OEP_WFP",
        "folder": "Workforce", "description": "Headcount and compensation planning.",
        "definition": {
            "application": APP, "cube": "OEP_WFP", "folder": "Workforce",
            "pov": [
                {"dimension": "Scenario", "selection": {"type": "member", "member": "Plan"}},
                {"dimension": "Version", "selection": {"type": "member", "member": "Working"}},
                {"dimension": "Years", "selection": {"type": "member", "member": "FY26"}},
            ],
            "pages": [
                {"dimension": "Entity", "selection": {"type": "userVariable", "variable": "CurrentEntity"}},
                {"dimension": "Job", "selection": {"type": "children", "member": "Total Jobs"}},
            ],
            "rows": [{"dimension": "Account", "selection": {"type": "levelZeroDescendants", "member": "Total Payroll"}, "suppressMissing": True}],
            "columns": [{"dimension": "Period", "selection": {"type": "range", "start": "Jan", "end": "Dec"}}],
            "display": {"useAliases": True, "suppressMissingRows": True},
        },
    },
]

# --- Rules -----------------------------------------------------------------
rules = [
    {
        "name": "Add New Hire", "application": APP, "cube": "OEP_WFP", "type": "groovy",
        "runtime_prompts": ["Employee", "Entity", "Job", "StartMonth", "AnnualSalary"],
        "has_source": True,
        "purpose": "Adds a new hire and spreads annual salary across periods from the start month.",
        "source": (
            "/* Groovy business rule (demo) */\n"
            "String employee = rtps.Employee.getEnteredValue()\n"
            "String entity = rtps.Entity.getEnteredValue()\n"
            "String startMonth = rtps.StartMonth.getEnteredValue()\n"
            "Double salary = rtps.AnnualSalary.getEnteredValueAsDouble()\n"
            "// ... deterministic spread of salary/12 from startMonth to Dec ...\n"
        ),
        "prompt_defs": [
            {"name": "Employee", "type": "text", "promptText": "New employee name", "required": True},
            {"name": "Entity", "type": "member", "dimension": "Entity", "promptText": "Home entity", "required": True},
            {"name": "Job", "type": "member", "dimension": "Job", "promptText": "Job", "required": True},
            {"name": "StartMonth", "type": "member", "dimension": "Period", "promptText": "Start month", "default": "Jul", "required": True},
            {"name": "AnnualSalary", "type": "numeric", "promptText": "Annual salary", "default": "90000", "required": True},
        ],
    },
    {
        "name": "IR", "application": APP, "cube": "OEP_FS", "type": "calcScript",
        "runtime_prompts": ["Scenario", "Entity"], "has_source": True,
        "purpose": "Incremental Rollup — aggregates the current slice for the chosen scenario/entity.",
        "source": (
            'FIX(&CurrYr, {Scenario}, "Working", {Entity})\n'
            "  AGG(\"Account\", \"Entity\");\n"
            "ENDFIX\n"
        ),
        "prompt_defs": [
            {"name": "Scenario", "type": "member", "dimension": "Scenario", "promptText": "Scenario", "default": "Forecast", "required": True},
            {"name": "Entity", "type": "member", "dimension": "Entity", "promptText": "Entity", "default": "{{CurrentEntity}}", "required": True},
        ],
    },
    {
        "name": "Aggregate Financials", "application": APP, "cube": "OEP_FS", "type": "businessRule",
        "runtime_prompts": ["Scenario", "Version", "Entity"], "has_source": False,
        "purpose": "Full aggregation of the Financials cube.",
        "prompt_defs": [
            {"name": "Scenario", "type": "member", "dimension": "Scenario", "default": "Actual", "required": True},
            {"name": "Version", "type": "member", "dimension": "Version", "default": "Working", "required": True},
            {"name": "Entity", "type": "member", "dimension": "Entity", "default": "Total Entity", "required": True},
        ],
    },
    {
        "name": "Calculate Cash", "application": APP, "cube": "OEP_DCSH", "type": "businessRule",
        "runtime_prompts": ["Entity", "Scenario"], "has_source": False,
        "purpose": "Recalculates the daily cash position.",
        "prompt_defs": [
            {"name": "Entity", "type": "member", "dimension": "Entity", "default": "{{CurrentEntity}}", "required": True},
            {"name": "Scenario", "type": "member", "dimension": "Scenario", "default": "Forecast", "required": True},
        ],
    },
]

variables = [
    {"name": "CurrYr", "application": APP, "scope": "substitution", "dimension": "Years", "value": "FY26"},
    {"name": "CurrMonth", "application": APP, "scope": "substitution", "dimension": "Period", "value": "Jul"},
    {"name": "CurrScenario", "application": APP, "scope": "substitution", "dimension": "Scenario", "value": "Forecast"},
    {"name": "ActualMonths", "application": APP, "scope": "substitution", "dimension": "Period", "value": "Jun"},
    {"name": "CurrentEntity", "application": APP, "scope": "user", "dimension": "Entity", "value": "US Operations"},
    {"name": "CurrentScenario", "application": APP, "scope": "user", "dimension": "Scenario", "value": "Forecast"},
]

applications = [{"name": APP, "type": "planning", "description": "MCW Planning & Close (demo)"}]

# add cube membership to dimensions
for d in DIMENSIONS:
    d["application"] = APP


def write(name, data):
    (HERE / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


write("applications.json", applications)
write("cubes.json", CUBES)
write("dimensions.json", DIMENSIONS)
write("members.json", members)
write("forms.json", forms)
write("rules.json", rules)
write("variables.json", variables)
print(f"wrote fixtures: {len(members)} members, {len(forms)} forms, {len(rules)} rules, {len(variables)} vars")
