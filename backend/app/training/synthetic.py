"""Synthetic training-pair generation for the form NLU task.

Manufactures guaranteed-correct pairs for "natural-language request →
FormSpecification JSON" plus edit pairs "current spec + edit instruction →
new spec JSON" — without a single hand-labelled example:

1. :func:`generate_spec` builds a random *valid* spec against real
   :class:`TenantMetadata` — only cube/dimension/member combinations that
   actually resolve to non-empty member lists are ever produced.
2. :func:`phrase_spec` renders several natural-language phrasings per spec
   using template + vocabulary variation that mirrors (and deliberately
   extends beyond) ``form_nlu``'s vocabulary. Each phrasing is tagged
   ``supported``/``paraphrase`` honestly: the deterministic parser is run on
   the phrase and the tag records whether it reproduced the key fields —
   measured, never assumed. Paraphrase pairs are the most valuable ones.
3. :func:`generate_edit_pair` phrases a supported edit operation, applies it
   through :func:`form_nlu.apply_edit`, and keeps the result only if it
   really changed the spec and the outcome still validates.

The label side is always checked by the app's own validator: any spec that
fails :func:`validate_form` with a blocking error is rejected. Every
prompt/completion string passes through :func:`redact_text` for consistency
with ``scripts.export_training_data`` (synthetic data should contain no
secrets — this keeps the invariant mechanical, not hopeful).

Everything is driven by a caller-supplied ``random.Random``: same seed →
identical corpus.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass

from ..agent import form_nlu
from ..artifacts.metadata import TenantMetadata
from ..artifacts.resolver import ResolutionError, resolve_selection
from ..artifacts.validation import validate_form
from ..schemas.form_spec import (
    AxisMember,
    BusinessRuleAssociation,
    FormSpecification,
    MemberSelection,
)
from ..security.redaction import redact_text

SCENARIOS = ["Actual", "Budget", "Forecast", "Plan"]

# --- phrasing vocabulary -----------------------------------------------------
# Mirrors form_nlu's SCENARIO_WORDS / SELECTION_WORDS / AXIS_WORDS and
# deliberately extends beyond them ("projection", "bottom level members",
# "everything under", ...). Whether the deterministic parser copes with a
# given rendering is measured per phrase in phrase_spec, never assumed here.

VERBS = ["Create", "Build", "Make", "Generate", "Set up", "Please create",
         "I need", "Can you put together", "We need", "Draft"]
PREFIXES = ["", "", "", "Hey, ", "Hi — ", "Quick one: "]
SUFFIXES = ["", "", "", ".", ". Thanks!", " when you get a chance."]

SCENARIO_PHRASES = {
    "Actual": ["Actuals", "Actual", "actuals"],
    "Budget": ["Budget", "budget", "budgeting"],
    "Forecast": ["Forecast", "forecast", "projection"],
    "Plan": ["Plan", "plan", "planning"],
}

CUBE_THEMES = {
    "OEP_FS": ["", "", "financial "],
    "OEP_WFP": ["workforce ", "payroll ", ""],
    "OEP_DCSH": ["cash ", "daily cash ", ""],
    "OEP_REP": ["reporting ", ""],
}

SELECTION_CLAUSES = {
    "children": ["children of {a}", "the children of {a}",
                 "the direct children of {a}", "each member directly under {a}"],
    "inclusiveChildren": ["inclusive children of {a}", "{a} and its children",
                          "{a} plus its children"],
    "descendants": ["descendants of {a}", "all descendants of {a}",
                    "everything under {a}", "the full subtree under {a}"],
    "inclusiveDescendants": ["inclusive descendants of {a}",
                             "{a} and everything below it"],
    "levelZeroDescendants": ["level-zero descendants of {a}",
                             "level zero descendants of {a}",
                             "level 0 descendants of {a}",
                             "the leaf level members under {a}",
                             "the bottom level members under {a}",
                             "the lowest-level members below {a}",
                             "leaf members of {a}"],
    "siblings": ["siblings of {a}", "the siblings of {a}", "the peers of {a}"],
    "member": ["just {a}", "only {a}", "a single row for {a}"],
}

ROW_TEMPLATES = ["with {sel} in rows", "with {sel} in the rows",
                 "showing {sel} on rows", "with rows of {sel}"]

EDIT_PROMPT = "Current form specification:\n{spec}\n\nEdit request: {instruction}"

# Selection-type wordings the deterministic editor understands ("change the
# rows to <wording>"). Never phrased as "use X instead of Y": form_nlu scans
# SELECTION_WORDS in a fixed order, so naming the old type too could make the
# editor pick it — and the label must follow the instruction's intent.
_SEL_WORDINGS = {
    "children": ["children"],
    "inclusiveChildren": ["inclusive children"],
    "descendants": ["descendants"],
    "inclusiveDescendants": ["inclusive descendants"],
    "levelZeroDescendants": ["level-zero descendants", "level zero descendants",
                             "level 0 descendants", "leaf level"],
    "siblings": ["siblings"],
}

# Hierarchy-function pool for row selections, weighted toward the common ones.
_ROW_SELECTION_POOL = (
    ["children"] * 3
    + ["levelZeroDescendants"] * 3
    + ["descendants"] * 2
    + ["inclusiveChildren", "inclusiveDescendants", "siblings"]
    + ["memberList"] * 2
    + ["member"]
)

_ROW_DIM_CANDIDATES = ["Account", "Entity", "Employee", "Job", "BankAccount"]
_CUBE_WEIGHTS = {"OEP_FS": 4, "OEP_WFP": 3, "OEP_DCSH": 2}


@dataclass(frozen=True)
class Phrase:
    """One natural-language rendering of a spec, honestly tagged."""

    text: str
    tag: str  # "supported" (parser reproduces the key fields) | "paraphrase"


@dataclass(frozen=True)
class TrainingPair:
    prompt: str
    completion: str
    kind: str  # "build" | "edit"
    tag: str | None = None  # build pairs only: "supported" | "paraphrase"


def spec_to_json(spec: FormSpecification) -> str:
    """Serialise a spec exactly like the exporter's artifact payloads
    (camelCase dict, ``indent=2, sort_keys=True``) so files concatenate."""
    return json.dumps(spec.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)


def pair_digest(prompt: str, completion: str) -> str:
    """Same sha256 dedup key as scripts.export_training_data."""
    return hashlib.sha256(f"{prompt}\x00{completion}".encode()).hexdigest()


# --- spec generation ---------------------------------------------------------


def generate_spec(md: TenantMetadata, rng: random.Random) -> FormSpecification:
    """Build a random FormSpecification that is valid against ``md``.

    Every selection is checked with the real resolver before it is placed, so
    the spec never references a missing member or an empty hierarchy, and the
    one-axis-per-dimension rule holds by construction.
    """
    cubes = list(md.cubes) or ["OEP_FS"]
    cube = rng.choices(cubes, weights=[_CUBE_WEIGHTS.get(c, 1) for c in cubes], k=1)[0]
    cube_dims = md.cubes[cube].dimensions if cube in md.cubes else []
    scenario = rng.choice(
        [s for s in SCENARIOS if md.get_member("Scenario", s)] or ["Actual"])

    row_dims = [d for d in _ROW_DIM_CANDIDATES if d in cube_dims and md.members.get(d)]
    if "Account" in row_dims and rng.random() < 0.6:
        row_dim = "Account"
    else:
        row_dim = rng.choice(row_dims or ["Account"])
    rows = _random_row_axis(md, row_dim, rng)
    columns = _random_columns(md, rng)

    version = rng.choice(["Working", "Working", "Working", "Final"])
    pov = [
        AxisMember(dimension="Scenario", selection=MemberSelection(type="member", member=scenario)),
        AxisMember(dimension="Version", selection=MemberSelection(type="member", member=version)),
    ]
    if "Years" in cube_dims and rng.random() < 0.25:
        years = _leaves(md, "Years")
        if years:
            pov.append(AxisMember(dimension="Years",
                                  selection=MemberSelection(type="member", member=rng.choice(years))))

    pages: list[AxisMember] = []
    if "Entity" in cube_dims and row_dim != "Entity":
        if md.get_variable("CurrentEntity") and rng.random() < 0.7:
            pages = [AxisMember(dimension="Entity",
                                selection=MemberSelection(type="userVariable", variable="CurrentEntity"))]
        else:
            parents = _parents(md, "Entity")
            if parents:
                pages = [AxisMember(dimension="Entity",
                                    selection=MemberSelection(type="member", member=rng.choice(parents)))]

    spec = FormSpecification(
        name=f"{scenario} {_theme(cube, rows)} Form"[:80],
        application=md.application,
        cube=cube,
        pov=pov,
        pages=pages,
        rows=[rows],
        columns=[columns],
    )

    if rng.random() < 0.25:
        spec.display.use_aliases = False
    if rng.random() < 0.2:
        spec.display.read_only = True
    if rng.random() < 0.2:
        try:
            col_members = resolve_selection(md, columns.dimension, columns.selection).members
        except ResolutionError:
            col_members = []
        if col_members:
            spec.display.hidden_members = rng.sample(
                col_members, rng.randint(1, min(2, len(col_members))))
    cube_rules = [r.name for r in md.rules.values() if r.cube == cube]
    if cube_rules and rng.random() < 0.25:
        spec.business_rule_associations = [BusinessRuleAssociation(rule_name=rng.choice(cube_rules))]
    return spec


def _random_row_axis(md: TenantMetadata, dim: str, rng: random.Random) -> AxisMember:
    for _ in range(20):
        sel_type = rng.choice(_ROW_SELECTION_POOL)
        if sel_type == "memberList":
            pool = _leaves(md, dim)
            if len(pool) < 2:
                continue
            selection = MemberSelection(
                type="memberList", members=rng.sample(pool, rng.randint(2, min(5, len(pool)))))
        elif sel_type == "member":
            pool = _parents(md, dim)
            if not pool:
                continue
            selection = MemberSelection(type="member", member=rng.choice(pool))
        elif sel_type == "siblings":
            pool = [m.name for m in md.members.get(dim, {}).values() if m.parent]
            if not pool:
                continue
            selection = MemberSelection(type="siblings", member=rng.choice(pool))
        else:
            pool = _parents(md, dim)
            if not pool:
                continue
            selection = MemberSelection(type=sel_type, member=rng.choice(pool))
        if _resolves(md, dim, selection):
            return AxisMember(dimension=dim, selection=selection, suppress_missing=True)
    # Deterministic fallback: the first parent's children always resolve.
    anchor = (_parents(md, dim) or list(md.member_order.get(dim, ["Total Account"])))[0]
    return AxisMember(dimension=dim,
                      selection=MemberSelection(type="children", member=anchor),
                      suppress_missing=True)


def _random_columns(md: TenantMetadata, rng: random.Random) -> AxisMember:
    candidates: list[MemberSelection] = []
    for start, end in (("Jan", "Dec"), ("Jan", "Dec"), ("Jan", "Dec"),
                       ("Jan", "Jun"), ("Jul", "Dec")):
        candidates.append(MemberSelection(type="range", start=start, end=end))
    quarters = [q for q in ("Q1", "Q2", "Q3", "Q4") if md.get_member("Period", q)]
    if quarters:
        candidates.append(MemberSelection(type="memberList", members=quarters))
    if md.get_member("Period", "YearTotal"):
        candidates.append(MemberSelection(type="children", member="YearTotal"))
    selection = rng.choice(candidates)
    if not _resolves(md, "Period", selection):
        leaves = _leaves(md, "Period") or ["Jan"]
        selection = MemberSelection(type="memberList", members=leaves[:12])
    return AxisMember(dimension="Period", selection=selection)


def _theme(cube: str, rows: AxisMember) -> str:
    anchor = (rows.selection.member or "").lower()
    if "payroll" in anchor:
        return "Payroll"
    if "revenue" in anchor:
        return "Revenue"
    if "expense" in anchor:
        return "Expense"
    return {"OEP_DCSH": "Cash", "OEP_WFP": "Workforce", "OEP_REP": "Reporting"}.get(cube, "Review")


# --- phrasing ----------------------------------------------------------------


def phrase_spec(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> list[Phrase]:
    """Render 2–5 distinct natural-language phrasings of ``spec``.

    Each phrase is tagged by actually running ``form_nlu.build_initial_spec``
    on it: ``supported`` if the parser reproduces the cube, the row selection
    (dimension + type + anchor) and the scenario; ``paraphrase`` otherwise.
    """
    target = rng.randint(2, 5)
    phrases: list[Phrase] = []
    seen: set[str] = set()
    for _ in range(target * 4):
        if len(phrases) >= target:
            break
        text = _render_phrase(spec, md, rng)
        if text in seen:
            continue
        seen.add(text)
        tag = "supported" if _parser_reproduces(text, spec, md) else "paraphrase"
        phrases.append(Phrase(text=redact_text(text), tag=tag))
    return phrases


def _render_phrase(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str:
    verb = rng.choice(VERBS)
    scenario = _axis_value(spec, "Scenario") or "Actual"
    scen_word = rng.choice(SCENARIO_PHRASES.get(scenario, [scenario]))
    theme = rng.choice(CUBE_THEMES.get(spec.cube, [""]))
    head = f"{scen_word} {theme}form"
    article = "an" if head[:1].lower() in "aeiou" else "a"
    row_clause = rng.choice(ROW_TEMPLATES).format(sel=_row_sel_clause(spec.rows[0], md, rng))
    clauses = [c for c in (_column_clause(spec.columns[0], rng),
                           *_extra_clauses(spec, rng)) if c]
    rng.shuffle(clauses)
    body = ", ".join([f"{verb} {article} {head} {row_clause}", *clauses])
    return f"{rng.choice(PREFIXES)}{body}{rng.choice(SUFFIXES)}"


def _row_sel_clause(am: AxisMember, md: TenantMetadata, rng: random.Random) -> str:
    sel = am.selection
    if sel.type == "memberList":
        return _join_names([_display_name(md, am.dimension, m, rng) for m in sel.members or []])
    anchor = _display_name(md, am.dimension, sel.member or "", rng)
    templates = SELECTION_CLAUSES.get(sel.type, ["{a}"])
    return rng.choice(templates).format(a=anchor)


def _column_clause(am: AxisMember, rng: random.Random) -> str:
    sel = am.selection
    if sel.type == "range":
        if (sel.start, sel.end) == ("Jan", "Dec"):
            # Jan:Dec is the conventional default — sometimes left unsaid.
            return rng.choice(["", "", "Jan through Dec in columns",
                               "months Jan to Dec across the columns",
                               "a full-year Jan:Dec column layout"])
        return rng.choice([f"{sel.start} through {sel.end} in columns",
                           f"columns from {sel.start} to {sel.end}",
                           f"{sel.start}:{sel.end} across the columns"])
    if sel.type == "memberList":
        lst = _join_names(sel.members or [])
        return rng.choice([f"{lst} in columns", "the four quarters as columns",
                           f"{lst} across the columns"])
    return rng.choice([f"the children of {sel.member} in columns",
                       f"quarter totals (children of {sel.member}) as columns"])


def _extra_clauses(spec: FormSpecification, rng: random.Random) -> list[str]:
    out: list[str] = []
    if rng.random() < 0.25:
        out.append(rng.choice([f"in cube {spec.cube}", f"in the {spec.cube} cube"]))
    version = next((am.selection.member for am in spec.pov if am.dimension == "Version"), None)
    if version and version != "Working":
        out.append(rng.choice([f"using the {version} version", f"against the {version} version"]))
    year = next((am.selection.member for am in spec.pov if am.dimension == "Years"), None)
    if year:
        out.append(rng.choice([f"for {year}", f"scoped to {year}"]))
    page = next((am for am in spec.pages if am.selection.type == "member"), None)
    if page:
        out.append(rng.choice([f"with {page.selection.member} as the page",
                               f"paged by {page.selection.member}"]))
    if not spec.display.use_aliases:
        out.append(rng.choice(["using technical member names",
                               "with technical names instead of aliases", "no aliases"]))
    if spec.display.read_only:
        out.append(rng.choice(["make it read-only", "as a read-only form"]))
    if spec.display.hidden_members:
        lst = _join_names(spec.display.hidden_members)
        out.append(rng.choice([f"hiding {lst}", f"with {lst} hidden"]))
    for assoc in spec.business_rule_associations:
        out.append(rng.choice([f"and attach the {assoc.rule_name} rule",
                               f"with the {assoc.rule_name} rule attached"]))
    return out


def _parser_reproduces(text: str, spec: FormSpecification, md: TenantMetadata) -> bool:
    """Would the deterministic parser get the key fields right for this phrase?"""
    try:
        parsed, _inferences, _questions = form_nlu.build_initial_spec(text, md, spec.application)
    except Exception:
        return False
    if parsed.cube != spec.cube:
        return False
    if _axis_value(parsed, "Scenario") != _axis_value(spec, "Scenario"):
        return False
    if not parsed.rows:
        return False
    got, want = parsed.rows[0], spec.rows[0]
    return (got.dimension == want.dimension
            and got.selection.type == want.selection.type
            and (got.selection.member or "") == (want.selection.member or ""))


# --- edit pairs --------------------------------------------------------------


def generate_edit_pair(
    spec: FormSpecification, md: TenantMetadata, rng: random.Random
) -> TrainingPair | None:
    """Phrase one supported edit, apply it via form_nlu.apply_edit, and return
    the pair — or None when the edit did not stick or the result is invalid."""
    ops = _applicable_edits(spec, md)
    if not ops:
        return None
    instruction = _EDIT_BUILDERS[rng.choice(ops)](spec, md, rng)
    if not instruction:
        return None
    candidate = spec.model_copy(deep=True)
    changed, _changes, _questions = form_nlu.apply_edit(candidate, instruction, md)
    old_json, new_json = spec_to_json(spec), spec_to_json(candidate)
    if not changed or new_json == old_json:
        return None
    try:  # the label must round-trip the schema and pass the app's validator
        reparsed = FormSpecification.model_validate(json.loads(new_json))
    except Exception:
        return None
    if validate_form(reparsed, md).blocking:
        return None
    prompt = EDIT_PROMPT.format(spec=old_json, instruction=instruction)
    return TrainingPair(prompt=redact_text(prompt), completion=redact_text(new_json), kind="edit")


def _applicable_edits(spec: FormSpecification, md: TenantMetadata) -> list[str]:
    ops = ["scenario", "aliases", "readOnly", "hide"]
    if _movable(spec):
        ops.append("move")
    if len(_resolve_axis(md, spec.rows[0])) >= 3:
        ops.append("limitRows")
    account = _first_account_member(spec)
    if account is not None and account.selection.member:
        ops.append("selectionType")
    attached = {a.rule_name.lower() for a in spec.business_rule_associations}
    if any(r.cube == spec.cube and r.name.lower() not in attached for r in md.rules.values()):
        ops.append("attachRule")
    if spec.columns and spec.columns[0].selection.type == "range":
        ops.append("reversePeriods")
    return ops


def _edit_scenario(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str | None:
    current = _axis_value(spec, "Scenario")
    options = [s for s in SCENARIOS if s != current and md.get_member("Scenario", s)]
    if not options:
        return None
    s = rng.choice(options)
    return rng.choice([f"change the scenario to {s}", f"use the {s} scenario",
                       f"switch the scenario to {s}"])


def _edit_aliases(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str:
    if spec.display.use_aliases:
        return rng.choice(["switch to technical names",
                           "show technical names instead of aliases",
                           "no aliases please", "use technical names"])
    return rng.choice(["use aliases", "show aliases on the form",
                       "please use aliases for the row labels"])


def _edit_read_only(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str:
    if spec.display.read_only:
        return rng.choice(["make the form editable", "make it editable again"])
    return rng.choice(["make the form read-only", "set the form to read only",
                       "make it read-only"])


def _edit_hide(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str | None:
    axis = rng.choice([spec.columns[0], spec.rows[0]])
    pool = [m for m in _resolve_axis(md, axis) if m not in spec.display.hidden_members]
    if not pool:
        return None
    chosen = rng.sample(pool, rng.randint(1, min(2, len(pool))))
    shown = [_display_name(md, axis.dimension, m, rng) for m in chosen]
    if len(shown) == 2:
        return rng.choice([f"hide {shown[0]} and {shown[1]}",
                           f"please hide {shown[0]} and {shown[1]}"])
    return rng.choice([f"hide {shown[0]}", f"can you hide {shown[0]}"])


def _edit_move(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str | None:
    moves = _movable(spec)
    if not moves:
        return None
    dim, target = rng.choice(moves)
    word = rng.choice({"pov": ["POV", "pov"], "pages": ["pages"], "rows": ["rows"]}[target])
    return rng.choice([f"move {dim} to {word}", f"put {dim} on {word}"])


def _edit_limit_rows(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str | None:
    count = len(_resolve_axis(md, spec.rows[0]))
    if count < 3:
        return None
    n = rng.randint(2, min(6, count - 1))
    return rng.choice([f"only show {n} rows", f"just show the first {n} rows",
                       f"show only {n} rows"])


def _edit_selection_type(
    spec: FormSpecification, md: TenantMetadata, rng: random.Random
) -> str | None:
    target = _first_account_member(spec)
    if target is None or not target.selection.member:
        return None
    options = [t for t in _SEL_WORDINGS if t != target.selection.type]
    wording = rng.choice(_SEL_WORDINGS[rng.choice(options)])
    return rng.choice([f"use {wording} instead", f"change the rows to {wording}",
                       f"use {wording} for the rows"])


def _edit_attach_rule(spec: FormSpecification, md: TenantMetadata, rng: random.Random) -> str | None:
    attached = {a.rule_name.lower() for a in spec.business_rule_associations}
    options = [r.name for r in md.rules.values()
               if r.cube == spec.cube and r.name.lower() not in attached]
    if not options:
        return None
    name = rng.choice(options)
    return rng.choice([f"attach the {name} rule", f"associate the {name} rule with this form"])


def _edit_reverse_periods(
    spec: FormSpecification, md: TenantMetadata, rng: random.Random
) -> str:
    return rng.choice(["reverse the period order", "reverse the periods"])


_EDIT_BUILDERS = {
    "scenario": _edit_scenario,
    "aliases": _edit_aliases,
    "readOnly": _edit_read_only,
    "hide": _edit_hide,
    "move": _edit_move,
    "limitRows": _edit_limit_rows,
    "selectionType": _edit_selection_type,
    "attachRule": _edit_attach_rule,
    "reversePeriods": _edit_reverse_periods,
}


def _movable(spec: FormSpecification) -> list[tuple[str, str]]:
    moves: list[tuple[str, str]] = []
    for am in spec.pages:
        if am.dimension == "Entity":
            moves += [("Entity", "pov"), ("Entity", "rows")]
    for am in spec.pov:
        if am.dimension in ("Version", "Years"):
            moves.append((am.dimension, "pages"))
    return moves


# --- corpus assembly ---------------------------------------------------------


def build_corpus(
    md: TenantMetadata,
    count: int,
    rng: random.Random,
    edits_ratio: float = 0.3,
) -> tuple[list[TrainingPair], dict]:
    """Generate ``count`` unique, validator-approved training pairs.

    ``edits_ratio`` steers the fraction of edit pairs. Duplicates (sha256 of
    prompt+completion, like the exporter) are dropped and counted; candidates
    whose spec fails validation are counted in ``validationRejected``.
    """
    pairs: list[TrainingPair] = []
    seen: set[str] = set()
    stats = {"buildPairs": 0, "editPairs": 0, "supported": 0, "paraphrase": 0,
             "duplicatesDropped": 0, "validationRejected": 0}

    def add(pair: TrainingPair) -> None:
        digest = pair_digest(pair.prompt, pair.completion)
        if digest in seen:
            stats["duplicatesDropped"] += 1
            return
        seen.add(digest)
        pairs.append(pair)
        if pair.kind == "edit":
            stats["editPairs"] += 1
        else:
            stats["buildPairs"] += 1
            stats[pair.tag] += 1

    attempts, max_attempts = 0, max(200, count * 60)
    while len(pairs) < count and attempts < max_attempts:
        attempts += 1
        spec = generate_spec(md, rng)
        if validate_form(spec, md).blocking:  # the guarantee, enforced
            stats["validationRejected"] += 1
            continue
        if stats["editPairs"] < edits_ratio * (len(pairs) + 1):
            pair = generate_edit_pair(spec, md, rng)
            if pair is None:
                stats["validationRejected"] += 1
                continue
            add(pair)
        else:
            completion = redact_text(spec_to_json(spec))
            for phrase in phrase_spec(spec, md, rng):
                if len(pairs) >= count:
                    break
                add(TrainingPair(prompt=phrase.text, completion=completion,
                                 kind="build", tag=phrase.tag))
    return pairs, stats


# --- small helpers -----------------------------------------------------------


def _axis_value(spec: FormSpecification, dimension: str) -> str | None:
    for am in spec.pov + spec.pages:
        if am.dimension == dimension:
            return am.selection.member
    return None


def _first_account_member(spec: FormSpecification) -> AxisMember | None:
    for _kind, am in spec.all_axis_members():
        if am.dimension == "Account":
            return am
    return None


def _resolve_axis(md: TenantMetadata, am: AxisMember) -> list[str]:
    try:
        return resolve_selection(md, am.dimension, am.selection).members
    except ResolutionError:
        return []


def _resolves(md: TenantMetadata, dimension: str, selection: MemberSelection) -> bool:
    try:
        return bool(resolve_selection(md, dimension, selection).members)
    except ResolutionError:
        return False


def _parents(md: TenantMetadata, dimension: str) -> list[str]:
    return [m.name for m in md.members.get(dimension, {}).values() if m.children]


def _leaves(md: TenantMetadata, dimension: str) -> list[str]:
    return [m.name for m in md.members.get(dimension, {}).values() if not m.children]


def _display_name(md: TenantMetadata, dimension: str, member: str, rng: random.Random) -> str:
    alias = md.alias_of(dimension, member)
    return alias if alias and rng.random() < 0.3 else member


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
