"""Deterministic natural-language report building & editing.

The report analogue of ``form_nlu``: turns phrases like "create a revenue report
by month in millions with a bar chart" into a ``ReportSpecification``, and edits
like "show as millions", "2 decimals", "red negatives", "highlight values over
500000 red", "add a line chart", or a per-cell "make this bold" / "set to 1200"
into precise, explainable spec changes — no LLM required.

Reuses ``form_nlu`` primitives (cube inference, member/selection matching) so the
report engine understands the same vocabulary as the form engine.
"""

from __future__ import annotations

import re

from ..artifacts.metadata import TenantMetadata
from ..schemas.form_spec import AxisMember, BusinessRuleAssociation, MemberSelection
from ..schemas.report_spec import (
    ChartType,
    ConditionalRule,
    NegativeStyle,
    ReportChart,
    ReportGrid,
    ReportSpecification,
    ReportType,
    SmartFormat,
)
from . import form_nlu

SCENARIO_WORDS = form_nlu.SCENARIO_WORDS


def _infer_smart_format(text: str) -> SmartFormat:
    tl = text.lower()
    fmt = SmartFormat()
    if any(w in tl for w in ("revenue", "cash", "dollar", "currency", "$", "cost", "expense", "budget", "financial")):
        fmt.prefix = "$"
    if "percent" in tl or "%" in tl or "variance" in tl:
        fmt.suffix = "%"
        fmt.prefix = ""
        fmt.decimal_places = 1
    if "million" in tl:
        fmt.scale = 6
        fmt.decimal_places = 1
    elif "thousand" in tl or " in k" in tl:
        fmt.scale = 3
        fmt.decimal_places = 0
    if "red negative" in tl or "negatives in red" in tl:
        fmt.negative_style = NegativeStyle.red
    return fmt


def _infer_chart(text: str) -> ReportChart | None:
    tl = text.lower()
    if "bar chart" in tl or "bar graph" in tl:
        return ReportChart(type=ChartType.bar)
    if "line chart" in tl or "trend" in tl:
        return ReportChart(type=ChartType.line)
    if "pie" in tl:
        return ReportChart(type=ChartType.pie)
    if "chart" in tl or "graph" in tl or "dashboard" in tl:
        return ReportChart(type=ChartType.bar)
    return None


def build_initial_report(
    text: str, md: TenantMetadata, application: str
) -> tuple[ReportSpecification, list[str], list[str]]:
    inferences: list[str] = []
    questions: list[str] = []
    tl = text.lower()

    cube = form_nlu._infer_cube(text, md)
    inferences.append(f"Cube: {cube} (inferred)")
    scenario = next((v for k, v in SCENARIO_WORDS.items() if re.search(rf"\b{k}\b", text, re.I)), "Actual")

    # rows: <function> of <member>, default children of Total Revenue
    sel_type = form_nlu._selection_type(text) or "children"
    member = form_nlu.find_member(md, text, dimension="Account")
    anchor = member[0] if member else "Total Revenue"
    rows = [AxisMember(dimension="Account", selection=MemberSelection(type=sel_type, member=anchor), suppress_missing=True)]
    inferences.append(f"Rows: {sel_type} of {anchor}")

    # columns: months by default, quarters if "quarter" mentioned
    if "quarter" in tl:
        columns = [AxisMember(dimension="Period",
                              selection=MemberSelection(type="memberList", members=["Q1", "Q2", "Q3", "Q4"]))]
        inferences.append("Columns: quarters")
    else:
        columns = [AxisMember(dimension="Period", selection=MemberSelection(type="range", start="Jan", end="Dec"))]
        inferences.append("Columns: Jan–Dec")

    pov = [
        AxisMember(dimension="Scenario", selection=MemberSelection(type="member", member=scenario)),
        AxisMember(dimension="Version", selection=MemberSelection(type="member", member="Working")),
    ]

    fmt = _infer_smart_format(text)
    chart = _infer_chart(text)
    report_type = ReportType.dashboard if (chart and "dashboard" in tl) else ReportType.grid

    grid = ReportGrid(
        name="Summary",
        pov=pov,
        rows=rows,
        columns=columns,
        smart_format=fmt,
        chart=chart,
        show_column_totals=True,
        show_row_totals="total" in tl,
    )
    spec = ReportSpecification(
        name=_derive_name(text, scenario),
        application=application,
        cube=cube,
        description=None,
        report_type=report_type,
        grids=[grid],
    )
    if chart:
        inferences.append(f"Chart: {chart.type}")
    return spec, inferences, questions


def _derive_name(text: str, scenario: str) -> str:
    tl = text.lower()
    theme = ("Revenue" if "revenue" in tl else "Cash" if "cash" in tl else
             "Workforce" if "workforce" in tl or "headcount" in tl else
             "Expense" if "expense" in tl or "cost" in tl else "Financial")
    return f"{scenario} {theme} Report"[:80]


# --- editing ----------------------------------------------------------------


def _apply_format_edit(fmt: SmartFormat, text: str) -> list[str]:
    tl = text.lower()
    changes: list[str] = []
    m = re.search(r"(\d+)\s*decimal", tl)
    if m:
        fmt.decimal_places = min(int(m.group(1)), 10)
        changes.append(f"Decimals → {fmt.decimal_places}")
    elif "no decimal" in tl or "whole number" in tl:
        fmt.decimal_places = 0
        changes.append("Decimals → 0")
    if "million" in tl:
        fmt.scale = 6
        changes.append("Scale → millions")
    elif "thousand" in tl or "in k" in tl:
        fmt.scale = 3
        changes.append("Scale → thousands")
    elif "no scal" in tl or "actual value" in tl or "unscaled" in tl:
        fmt.scale = 0
        changes.append("Scale → none")
    if "currency" in tl or "dollar" in tl or "$" in tl:
        fmt.prefix = "$"
        changes.append("Currency prefix $")
    if "percent" in tl or "%" in tl:
        fmt.suffix = "%"
        changes.append("Percent suffix %")
    if "parenthes" in tl and "red" in tl:
        fmt.negative_style = NegativeStyle.red_parentheses
        changes.append("Negatives → red parentheses")
    elif "parenthes" in tl:
        fmt.negative_style = NegativeStyle.parentheses
        changes.append("Negatives → parentheses")
    elif "red negative" in tl or "negatives in red" in tl or "red" in tl:
        fmt.negative_style = NegativeStyle.red
        changes.append("Negatives → red")
    if "no separator" in tl or "no comma" in tl:
        fmt.thousands_separator = False
        changes.append("Thousands separator off")
    # conditional highlight: "highlight values over 500000 red"
    m = re.search(r"(?:highlight|flag|colou?r)\s+(?:values?\s+)?(over|above|under|below|greater than|less than)\s+([\d,\.]+)", tl)
    if m:
        op = m.group(1)
        val = float(m.group(2).replace(",", ""))
        comparator = "gt" if op in ("over", "above", "greater than") else "lt"
        color = "#da1e28" if "red" in tl else "#0e6027" if "green" in tl else "#8a3ffc"
        fmt.conditional_rules.append(ConditionalRule(comparator=comparator, value=val, color=color, bold=True))
        changes.append(f"Conditional: {comparator} {val:g} → colour")
    return changes


def apply_report_edit(spec: ReportSpecification, text: str, md: TenantMetadata) -> tuple[bool, list[str], list[str]]:
    """Report-wide conversational edit (operates on the first grid by default)."""
    changes: list[str] = []
    questions: list[str] = []
    tl = text.lower()
    grid = spec.grids[0]

    # display aliases
    if "use alias" in tl or "show alias" in tl:
        if not spec.display.use_aliases:
            spec.display.use_aliases = True
            changes.append("Display: technical names → aliases")
    if "technical name" in tl or "no alias" in tl:
        if spec.display.use_aliases:
            spec.display.use_aliases = False
            changes.append("Display: aliases → technical names")

    # totals
    if "row total" in tl or "totals per row" in tl:
        grid.show_row_totals = True
        changes.append("Row totals on")
    if "no column total" in tl or "hide total" in tl:
        grid.show_column_totals = False
        changes.append("Column totals off")
    elif "column total" in tl or "show total" in tl:
        grid.show_column_totals = True
        changes.append("Column totals on")

    # chart
    for word, ctype in (("bar", ChartType.bar), ("line", ChartType.line), ("pie", ChartType.pie), ("area", ChartType.area)):
        if f"{word} chart" in tl or (word == "line" and "trend" in tl):
            grid.chart = ReportChart(type=ctype, title=grid.chart.title if grid.chart else None)
            changes.append(f"Chart → {ctype.value}")
            break
    if "remove chart" in tl or "no chart" in tl:
        grid.chart = None
        changes.append("Chart removed")

    # selection type on Account rows: reuse form vocabulary
    sel = form_nlu._selection_type(text)
    if sel and ("instead" in tl or "use " in tl or "change" in tl):
        member = form_nlu.find_member(md, text, dimension="Account")
        target = next((am for am in grid.rows if am.dimension == "Account"), None)
        if target:
            anchor = member[0] if member else target.selection.member
            if anchor:
                target.selection = MemberSelection(type=sel, member=anchor)
                changes.append(f"Account rows → {sel} of {anchor}")

    # scenario
    scen = next((v for k, v in SCENARIO_WORDS.items() if re.search(rf"\b{k}\b", text, re.I)), None)
    if scen and ("scenario" in tl or "change" in tl or "use" in tl):
        for am in grid.pov:
            if am.dimension == "Scenario":
                am.selection = MemberSelection(type="member", member=scen)
                changes.append(f"Scenario → {scen}")
                break

    # attach a rule
    m = re.search(r"\b(attach|associate|add)\s+(the\s+)?([\w \-]+?)\s+rule\b", text, re.I)
    if m:
        rule_name = form_nlu._match_rule(md, m.group(3))
        if rule_name and rule_name.lower() not in [a.rule_name.lower() for a in spec.business_rule_associations]:
            spec.business_rule_associations.append(BusinessRuleAssociation(rule_name=rule_name))
            changes.append(f"Business rule attached: {rule_name}")

    # formatting (grid default)
    changes += _apply_format_edit(grid.smart_format, text)
    return (bool(changes), changes, questions)


def apply_table_edit(spec: ReportSpecification, grid_index: int, text: str, md: TenantMetadata) -> tuple[bool, list[str], list[str]]:
    """Edit scoped to a single grid/table (used by the panel's per-table prompt)."""
    if not (0 <= grid_index < len(spec.grids)):
        return (False, [], ["That table no longer exists."])
    # Temporarily target the chosen grid by swapping it to position 0 semantics:
    grid = spec.grids[grid_index]
    saved = spec.grids
    spec.grids = [grid]
    try:
        changed, changes, questions = apply_report_edit(spec, text, md)
    finally:
        spec.grids = saved
    return changed, [f"[{grid.name}] {c}" for c in changes], questions


def apply_cell_edit(
    spec: ReportSpecification, grid_index: int, row_label: str, column_label: str, text: str, md: TenantMetadata
) -> tuple[bool, list[str], list[str]]:
    """Edit scoped to one cell (the panel's per-cell prompt)."""
    from ..schemas.report_spec import CellOverride

    if not (0 <= grid_index < len(spec.grids)):
        return (False, [], ["That table no longer exists."])
    grid = spec.grids[grid_index]
    key = f"{row_label}||{column_label}"
    override = grid.cell_overrides.get(key) or CellOverride()
    changes: list[str] = []
    tl = text.lower()

    m = re.search(r"\bset\s+(?:to|it to|value to)?\s*\$?([\-\d,\.]+)", tl)
    if m:
        try:
            override.value = float(m.group(1).replace(",", "").replace("$", ""))
            changes.append(f"Value → {override.value:g}")
        except ValueError:
            pass

    fmt = override.format or SmartFormat()
    fmt_changes = _apply_format_edit(fmt, text)
    if "bold" in tl:
        fmt.conditional_rules.append(ConditionalRule(comparator="ge", value=-1e18, bold=True))
        changes.append("Bold")
    if "red" in tl and not fmt_changes:
        fmt.conditional_rules.append(ConditionalRule(comparator="ge", value=-1e18, color="#da1e28"))
        changes.append("Colour → red")
    if "highlight" in tl and "over" not in tl and "above" not in tl:
        fmt.conditional_rules.append(ConditionalRule(comparator="ge", value=-1e18, background="#fff8b3"))
        changes.append("Highlighted")
    if fmt_changes or fmt.conditional_rules:
        override.format = fmt
        changes += fmt_changes

    m = re.search(r"note[:\s]+(.+)$", text, re.I)
    if m:
        override.note = m.group(1).strip()[:200]
        changes.append("Note added")

    if changes:
        grid.cell_overrides[key] = override
        return (True, [f"[{row_label} · {column_label}] {c}" for c in changes], [])
    return (False, [], ["Try: *set to 1200*, *make it bold red*, *highlight*, or *note: ...*"])
