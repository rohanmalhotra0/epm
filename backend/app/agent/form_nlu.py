"""Deterministic natural-language form building & editing (spec sections 22, 25).

Turns phrases like "create an Actuals form with level-zero descendants of Total
Payroll in rows" and edits like "hide March", "move Entity to POV", "use
descendants instead of children" into precise FormSpecification changes — no LLM
required, fully reproducible. The model may propose specs too, but this path
guarantees the demo works offline and every change is explainable.
"""

from __future__ import annotations

import re

from ..artifacts.metadata import TenantMetadata
from ..artifacts.parser import clone_from_reference
from ..artifacts.resolver import resolve_selection
from ..schemas.form_spec import (
    AxisMember,
    BusinessRuleAssociation,
    FormSpecification,
    MemberSelection,
)
from . import outline_defaults as od

SCENARIO_WORDS = {
    "actuals": "Actual", "actual": "Actual", "forecast": "Forecast",
    "budget": "Budget", "plan": "Plan",
}
AXIS_WORDS = {
    "pov": "pov", "point of view": "pov", "page": "pages", "pages": "pages",
    "row": "rows", "rows": "rows", "column": "columns", "columns": "columns",
}
# order longest-first so "level-zero descendants" wins over "descendants"
SELECTION_WORDS = [
    ("level-zero descendants", "levelZeroDescendants"),
    ("level zero descendants", "levelZeroDescendants"),
    ("level 0 descendants", "levelZeroDescendants"),
    ("leaf level", "levelZeroDescendants"),
    ("inclusive descendants", "inclusiveDescendants"),
    ("inclusive children", "inclusiveChildren"),
    ("descendants", "descendants"),
    ("children", "children"),
    ("ancestors", "ancestors"),
    ("siblings", "siblings"),
]
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
            "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
            "last": -1}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def find_member(md: TenantMetadata, text: str, dimension: str | None = None) -> tuple[str, str] | None:
    """Longest technical-name/alias match present in the text -> (member, dimension)."""
    tl = text.lower()
    best: tuple[str, str] | None = None
    best_len = 0
    dims = [dimension] if dimension else list(md.members.keys())
    for dim in dims:
        for member in md.members.get(dim, {}).values():
            for candidate in (member.name, member.alias):
                if candidate and candidate.lower() in tl and len(candidate) > best_len:
                    best = (member.name, dim)
                    best_len = len(candidate)
    return best


def find_members(md: TenantMetadata, text: str, dimension: str | None = None) -> list[tuple[str, str]]:
    """Every distinct member whose technical name or alias appears in the text,
    ordered by first appearance. Uses the same substring matching as
    :func:`find_member`, so "March" still resolves to "Mar"."""
    tl = text.lower()
    hits: list[tuple[int, str, str]] = []  # (position, member, dimension)
    seen: set[tuple[str, str]] = set()
    dims = [dimension] if dimension else list(md.members.keys())
    for dim in dims:
        for member in md.members.get(dim, {}).values():
            key = (member.name, dim)
            if key in seen:
                continue
            for candidate in (member.name, member.alias):
                if candidate and (pos := tl.find(candidate.lower())) != -1:
                    hits.append((pos, member.name, dim))
                    seen.add(key)
                    break
    hits.sort(key=lambda h: h[0])
    return [(name, dim) for _pos, name, dim in hits]


def _detect_scenario(text: str, exclude: str | None = None) -> str | None:
    """First scenario word to appear in the text (by position). ``exclude`` (a
    referenced form's name) is blanked out first so its words aren't read as the
    user's scenario intent."""
    scan = re.sub(re.escape(exclude), " ", text, flags=re.I) if exclude else text
    best_pos: int | None = None
    best_val: str | None = None
    for word, value in SCENARIO_WORDS.items():
        m = re.search(rf"\b{re.escape(word)}\b", scan, re.I)
        if m and (best_pos is None or m.start() < best_pos):
            best_pos, best_val = m.start(), value
    return best_val


def _selection_type(text: str) -> str | None:
    tl = text.lower()
    for phrase, sel in SELECTION_WORDS:
        if phrase in tl:
            return sel
    return None


def _infer_cube(text: str, md: TenantMetadata) -> str:
    tl = text.lower()
    if "payroll" in tl or "workforce" in tl or "headcount" in tl or "hire" in tl:
        if md.has_cube("OEP_WFP"):
            return "OEP_WFP"
    if "cash" in tl and md.has_cube("OEP_DCSH"):
        return "OEP_DCSH"
    return "OEP_FS" if md.has_cube("OEP_FS") else next(iter(md.cubes), "OEP_FS")


# "like the SOFR loan form", "based on Actual Revenue Review" -> the name asked for.
# Stops at a conjunction so "like the SOFR loan but fully working" doesn't swallow
# the rest of the sentence.
_REFERENCE_PHRASE = re.compile(
    r"\b(?:like|based on|similar to|modelled on|modeled on)\s+(?:the\s+)?"
    r"([\w][\w\- ]{1,40}?)(?=\s+(?:form|but|and|with|that|which|for)\b|[.,?!]|$)",
    re.I,
)


def _referenced_name(text: str) -> str | None:
    m = _REFERENCE_PHRASE.search(text)
    return m.group(1).strip() if m else None


def _find_reference(text: str, md: TenantMetadata) -> str | None:
    tl = text.lower()
    if not any(w in tl for w in ("like", "based on", "template", "similar to", "as the")):
        # still allow explicit form name match
        pass
    for form in md.forms.values():
        if form.name.lower() in tl:
            return form.name
    return None


def build_initial_spec(
    text: str, md: TenantMetadata, application: str
) -> tuple[FormSpecification, list[str], list[str]]:
    inferences: list[str] = []
    questions: list[str] = []

    reference = _find_reference(text, md)
    # Detect the scenario from the user's own words, not from a referenced form's
    # name — "forecast form based on Actual Revenue Review" is Forecast, not Actual.
    scenario = _detect_scenario(text, exclude=reference)

    if reference and reference.lower() in md.forms:
        ref_def = md.forms[reference.lower()].definition or {}
        spec = clone_from_reference(ref_def, _derive_name(text, scenario, ref_def.get("cube", "")), reference)
        inferences.append(f"Reference form: {reference}")
    else:
        cube = _infer_cube(text, md)
        spec = _default_spec(md, cube=cube, application=application, scenario=scenario)
        inferences.append(f"Cube: {cube} (inferred)")
        # Don't quietly hand back a generic form when the user asked for a copy
        # of a specific one — say why the reference couldn't be used.
        if asked := _referenced_name(text):
            questions.append(
                f'I couldn\'t find a form called "{asked}" in this application, so this one is '
                f"built from scratch — which existing form should I copy?" if md.forms else
                f'I can\'t copy "{asked}" — forms aren\'t part of the loaded context, because the '
                f"core REST metadata API doesn't expose them. Import them via Migration, or tell "
                f"me the rows and columns you want and I'll build it directly.")

    if scenario:
        # Only the user's own word is tried here — if they asked for Forecast and
        # the outline has no Forecast, say so rather than quietly using Actual.
        scen_dim = od.find_dimension(md, "scenario", cube=spec.cube)
        resolved = od.resolve_member(md, scen_dim, scenario) if scen_dim else None
        if scen_dim and resolved:
            _set_pov_member(spec, scen_dim, resolved)
            inferences.append(f"Scenario: {resolved}" if resolved == scenario
                              else f"Scenario: {resolved} (matched \"{scenario}\")")
        else:
            questions.append(
                f"I couldn't find a '{scenario}' member in the "
                f"{scen_dim or 'Scenario'} dimension — which scenario should this form use?")

    # rows selection: "<function> of <member> in rows" — the anchor member may
    # belong to any dimension (Account, Employee, Entity, ...), not just Account.
    sel_type = _selection_type(text)
    member = find_member(md, text)
    if member and (sel_type or "row" in text.lower()):
        sel_type = sel_type or "children"
        if (dim := _set_rows(spec, member[1], sel_type, member[0])) is not None:
            inferences.append(f"Rows: {sel_type} of {member[0]} ({dim})")
        else:
            questions.append(
                f"{member[1]} is already on the columns of this form — should I put "
                f"{member[0]} on the rows and move {member[1]} to the POV?")

    # limit "N rows"
    n = _extract_count(text)
    if n and spec.rows:
        _limit_axis(spec.rows[0], md, n)
        inferences.append(f"Row limit: {n} members")

    # Anything still unplaced would otherwise be silently defaulted by the
    # renderer; pinning it here keeps the grid deterministic and visible.
    if added := od.fill_pov(md, spec, spec.cube):
        inferences.append(f"POV: {', '.join(added)} (defaulted)")

    spec.name = _derive_name(text, scenario, spec.cube)
    spec.application = application
    return spec, inferences, questions


def apply_edit(spec: FormSpecification, text: str, md: TenantMetadata) -> tuple[bool, list[str], list[str]]:
    """Apply one or more conversational edits. Returns (changed, changes, questions)."""
    changes: list[str] = []
    questions: list[str] = []
    tl = text.lower()

    # aliases
    if "use alias" in tl or "show alias" in tl:
        if not spec.display.use_aliases:
            spec.display.use_aliases = True
            changes.append("Display: technical names → aliases")
    if "technical name" in tl or "no alias" in tl:
        if spec.display.use_aliases:
            spec.display.use_aliases = False
            changes.append("Display: aliases → technical names")

    # read-only
    if "read-only" in tl or "read only" in tl:
        if not spec.display.read_only:
            spec.display.read_only = True
            changes.append("Form set to read-only")
    if "editable" in tl and spec.display.read_only:
        spec.display.read_only = False
        changes.append("Form set to editable")

    # move dimension between axes: "move Entity to POV" / "put Entity on Pages"
    m = re.search(r"\b(?:move|put|place)\s+([\w \-]+?)\s+(?:to|on|in|into)\s+(pov|point of view|pages?|rows?|columns?)\b", text, re.I)
    if m:
        dim = _match_dimension(spec, md, m.group(1))
        target = AXIS_WORDS.get(m.group(2).lower())
        if dim and target and _move_dimension(spec, dim, target):
            changes.append(f"{dim}: moved to {target}")

    # change selection type: "use descendants instead of children" / "use level-zero descendants"
    sel = _selection_type(text)
    if sel and ("instead" in tl or "use " in tl or "change" in tl):
        # Retarget whatever dimension is actually on rows — it is the account
        # dimension on a default form, but not on one built from a reference.
        target_am = spec.rows[0] if spec.rows else None
        if target_am:
            member = find_member(md, text, dimension=target_am.dimension)
            anchor = member[0] if member else target_am.selection.member
            if anchor:
                target_am.selection = MemberSelection(type=sel, member=anchor)
                changes.append(f"{target_am.dimension} rows: selection → {sel} of {anchor}")

    # hide member by name or ordinal column/row
    changes += _apply_hide(spec, text, md)

    # limit "only show N (members/rows)"
    n = _extract_count(text)
    if n and ("only" in tl or "just" in tl or "show" in tl) and spec.rows:
        _limit_axis(spec.rows[0], md, n)
        changes.append(f"Rows limited to {n} members")

    # remove dimension: "remove the X dimension"
    m = re.search(r"\bremove\s+(the\s+)?([\w \-]+?)\s+dimension\b", text, re.I)
    if m:
        dim = _match_dimension(spec, md, m.group(2))
        if dim and _remove_dimension(spec, dim):
            changes.append(f"{dim}: removed from the form")

    # reverse periods
    if "reverse" in tl and "period" in tl:
        for am in spec.columns:
            if am.dimension == "Period" and am.selection.type == "range":
                am.selection.start, am.selection.end = am.selection.end, am.selection.start
                changes.append("Columns: period order reversed")

    # attach a rule: "attach the IR rule" / "associate that rule"
    m = re.search(r"\b(attach|associate|add)\s+(the\s+)?([\w \-]+?)\s+rule\b", text, re.I)
    if m:
        rule_name = _match_rule(md, m.group(3))
        if rule_name and rule_name.lower() not in [a.rule_name.lower() for a in spec.business_rule_associations]:
            spec.business_rule_associations.append(BusinessRuleAssociation(rule_name=rule_name))
            changes.append(f"Business rule attached: {rule_name}")

    # change scenario: "change scenario to Forecast" / "use Forecast scenario"
    scen = _detect_scenario(text)
    if scen and ("scenario" in tl or "change" in tl or "use" in tl):
        scen_dim = od.find_dimension(md, "scenario", cube=spec.cube)
        resolved = od.resolve_member(md, scen_dim, scen) if scen_dim else None
        if scen_dim and resolved:
            _set_pov_member(spec, scen_dim, resolved)
            changes.append(f"Scenario → {resolved}")
        else:
            questions.append(f"There's no '{scen}' member in the "
                             f"{scen_dim or 'Scenario'} dimension — which scenario did you mean?")

    return (bool(changes), changes, questions)


# --- helpers ----------------------------------------------------------------


def _default_spec(
    md: TenantMetadata, application: str, cube: str, scenario: str | None
) -> FormSpecification:
    """Skeleton form built from the tenant's own outline.

    Every dimension is located by its declared type and every member is resolved
    against the outline, so the skeleton is valid on any application — not just
    ones that happen to use the Planning-standard names.
    """
    pov: list[AxisMember] = []
    pages: list[AxisMember] = []
    rows: list[AxisMember] = []
    columns: list[AxisMember] = []

    scen_dim = od.find_dimension(md, "scenario", cube=cube)
    if scen_dim and (sel := od.pov_selection(md, scen_dim, scenario, *od.SCENARIO_DEFAULTS)):
        pov.append(AxisMember(dimension=scen_dim, selection=sel))

    ver_dim = od.find_dimension(md, "version", cube=cube)
    if ver_dim and (sel := od.pov_selection(md, ver_dim, *od.VERSION_DEFAULTS)):
        pov.append(AxisMember(dimension=ver_dim, selection=sel))

    ent_dim = od.find_dimension(md, "entity", cube=cube)
    if ent_dim and (sel := od.page_selection(md, ent_dim)):
        pages.append(AxisMember(dimension=ent_dim, selection=sel))

    acct_dim = od.find_dimension(md, "account", cube=cube)
    if acct_dim and (anchor := od.anchor_member(md, acct_dim, *od.ROW_ANCHOR_DEFAULTS)):
        rows.append(AxisMember(dimension=acct_dim, suppress_missing=True,
                               selection=MemberSelection(type="children", member=anchor)))

    per_dim = od.find_dimension(md, "period", cube=cube)
    if per_dim and (sel := od.period_columns(md, per_dim)):
        columns.append(AxisMember(dimension=per_dim, selection=sel))

    # A grid needs both axes. An application without an account- or period-typed
    # dimension is unusual but legal, so borrow any unplaced dimension rather
    # than failing spec construction outright.
    used = {am.dimension for am in pov + pages + rows + columns}
    for axis, anchored in ((rows, True), (columns, False)):
        if axis:
            continue
        for dim in od.cube_dimensions(md, cube):
            if dim in used or (member := od.anchor_member(md, dim)) is None:
                continue
            axis.append(AxisMember(dimension=dim, suppress_missing=anchored,
                                   selection=MemberSelection(type="children", member=member)))
            used.add(dim)
            break

    return FormSpecification(
        name="New Form", application=application, cube=cube, folder="EPM Wizard/Generated",
        pov=pov, pages=pages, rows=rows, columns=columns,
    )


def _derive_name(text: str, scenario: str | None, cube: str) -> str:
    tl = text.lower()
    theme = "Payroll" if "payroll" in tl else ("Revenue" if "revenue" in tl else
            ("Cash" if "cash" in tl else ("Workforce" if "workforce" in tl or "hire" in tl else "Review")))
    prefix = scenario or "New"
    name = f"{prefix} {theme} Form".replace("New Review Form", "New Form")
    return name[:80]


def _set_pov_member(spec: FormSpecification, dimension: str, member: str) -> bool:
    for am in spec.pov + spec.pages:
        if am.dimension == dimension:
            am.selection = MemberSelection(type="member", member=member)
            return True
    spec.pov.append(AxisMember(dimension=dimension, selection=MemberSelection(type="member", member=member)))
    return True


def _set_rows(spec: FormSpecification, dimension: str, sel_type: str, member: str) -> str | None:
    """Place a single-dimension row selection, keeping the spec structurally valid.

    Returns the dimension used, or None if it couldn't be placed. The dimension is
    freed from POV/Pages if the skeleton parked it there (e.g. Entity). A collision
    with a column dimension is refused outright: the old code retargeted rows at
    Account while keeping the anchor member from the *other* dimension, which
    produced a spec that could never resolve."""
    if any(am.dimension == dimension for am in spec.columns):
        return None
    for axis in ("pov", "pages"):
        lst = _axis_list(spec, axis)
        for am in list(lst):
            if am.dimension == dimension:
                lst.remove(am)
    spec.rows = [AxisMember(dimension=dimension,
                            selection=MemberSelection(type=sel_type, member=member),
                            suppress_missing=True)]
    return dimension


def _first_axis_member(spec: FormSpecification, dimension: str) -> AxisMember | None:
    for _kind, am in spec.all_axis_members():
        if am.dimension == dimension:
            return am
    return None


def _match_dimension(spec: FormSpecification, md: TenantMetadata, phrase: str) -> str | None:
    phrase = phrase.strip().lower()
    for dim in md.dimensions:
        if dim.lower() == phrase or dim.lower() in phrase or phrase in dim.lower():
            return dim
    for _kind, am in spec.all_axis_members():
        if am.dimension.lower() in phrase:
            return am.dimension
    return None


def _match_rule(md: TenantMetadata, phrase: str) -> str | None:
    phrase = phrase.strip().lower()
    if not phrase:
        return None
    # exact match wins; then whole-word match (avoids "IR" hitting "h(ir)e")
    for rule in md.rules.values():
        if rule.name.lower() == phrase:
            return rule.name
    word = re.compile(rf"\b{re.escape(phrase)}\b", re.I)
    for rule in md.rules.values():
        if word.search(rule.name):
            return rule.name
    return None


def _axis_list(spec: FormSpecification, axis: str) -> list[AxisMember]:
    return {"pov": spec.pov, "pages": spec.pages, "rows": spec.rows, "columns": spec.columns}[axis]


def _move_dimension(spec: FormSpecification, dimension: str, target: str) -> bool:
    found: AxisMember | None = None
    for axis in ("pov", "pages", "rows", "columns"):
        lst = _axis_list(spec, axis)
        for am in list(lst):
            if am.dimension == dimension:
                found = am
                lst.remove(am)
    if found is None:
        return False
    # POV/Pages need a single member; convert a multi-member selection sensibly
    if target in ("pov", "pages") and found.selection.type not in ("member", "userVariable", "substitutionVariable"):
        found.selection = MemberSelection(type="member", member=found.selection.member or dimension)
    _axis_list(spec, target).append(found)
    return True


def _remove_dimension(spec: FormSpecification, dimension: str) -> bool:
    removed = False
    for axis in ("pov", "pages", "rows", "columns"):
        lst = _axis_list(spec, axis)
        for am in list(lst):
            if am.dimension == dimension:
                lst.remove(am)
                removed = True
    return removed


def _extract_count(text: str) -> int | None:
    m = re.search(r"\b(\d+)\s+(rows|members|columns)\b", text, re.I)
    if m:
        return int(m.group(1))
    for word, n in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\s+(rows|members|columns)\b", text, re.I):
            return n
    return None


def _limit_axis(am: AxisMember, md: TenantMetadata, n: int) -> None:
    try:
        members = resolve_selection(md, am.dimension, am.selection).members[:n]
    except Exception:
        return
    if members:
        am.selection = MemberSelection(type="memberList", members=members)


def _apply_hide(spec: FormSpecification, text: str, md: TenantMetadata) -> list[str]:
    tl = text.lower()
    if "hide" not in tl and "remove" not in tl:
        return []
    changes: list[str] = []
    # ordinal column/row
    m = re.search(r"hide\s+the\s+(\w+)\s+(column|row)\b", tl)
    if m:
        ordinal = ORDINALS.get(m.group(1))
        if ordinal is None and m.group(1).isdigit():
            ordinal = int(m.group(1))
        axis = spec.columns if m.group(2) == "column" else spec.rows
        if ordinal and axis:
            am = axis[0]
            try:
                members = resolve_selection(md, am.dimension, am.selection).members
                idx = ordinal - 1 if ordinal > 0 else len(members) - 1
                if 0 <= idx < len(members):
                    member = members[idx]
                    if member not in spec.display.hidden_members:
                        spec.display.hidden_members.append(member)
                        changes.append(f"Hidden {m.group(2)}: {member}")
                    return changes
            except Exception:
                pass
    # hide by member name/alias — capture every member named, not just the first
    # ("hide March and April" hides both).
    for name, _dim in find_members(md, text):
        if name not in spec.display.hidden_members:
            spec.display.hidden_members.append(name)
            changes.append(f"Hidden member: {name}")
    return changes
