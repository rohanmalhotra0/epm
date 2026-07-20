"""Outline-derived defaults for generated forms and reports.

The form/report builders used to emit Planning-standard boilerplate: Scenario
``Actual``, Version ``Working``, an ``Account`` dimension anchored on ``Total
Revenue``, Pages on ``{CurrentEntity}``, columns ``Jan:Dec``. Those names all
exist in the bundled MCW fixtures, so the tests passed — but a real EPBCS tenant
names the same concepts ``OEP_Actual`` / ``OEP_Working`` / ``Line Item``, and
every generated form failed validation before the user ever saw a grid.

Everything here resolves against the tenant outline instead: dimensions by their
declared ``type``, members by exact -> alias -> vendor-prefix-tolerant match, and
axis anchors by walking the real hierarchy. Nothing is invented — each helper
returns ``None`` when the outline has no sensible answer, and the caller omits
that part of the spec rather than emitting a name that cannot resolve.

This is deliberately *not* fuzzy resolution: ``resolver.py`` stays exact, because
a deployed artifact must never contain a member the user did not ask for. The
tolerance lives here, at generation time, where the alternative is a guaranteed
validation error rather than a wrong deployment.
"""

from __future__ import annotations

import re

from ..artifacts.metadata import TenantMetadata
from ..schemas.form_spec import AxisMember, MemberSelection

# Prefixes Oracle ships on seeded content (OEP_ = Planning, OWP_ = Workforce,
# OFS_ = Financials, OPF_ = Projects, OCX_ = Capital). A tenant's "Actual" is very
# often literally "OEP_Actual", so we try both directions before giving up.
VENDOR_PREFIXES = ("OEP_", "OWP_", "OFS_", "OPF_", "OCX_", "OGS_")

# Fallbacks tried in order when the outline is searched for a well-known concept.
SCENARIO_DEFAULTS = ("Actual", "Actuals")
VERSION_DEFAULTS = ("Working", "BU Version_1", "Final")
ROW_ANCHOR_DEFAULTS = ("Total Revenue", "Total Account", "Total Line Item")


def find_dimension(
    md: TenantMetadata, *types: str, cube: str | None = None
) -> str | None:
    """First dimension whose declared ``type`` matches, preferring one in ``cube``.

    This is what replaces the literal ``"Account"``: the account-type dimension
    is named ``Account`` in the fixtures and ``Line Item`` in MCW_PCF, but both
    are declared ``type="account"``.
    """
    wanted = {t.lower() for t in types}
    fallback: str | None = None
    for name, dim in md.dimensions.items():
        if (dim.type or "generic").lower() not in wanted:
            continue
        if cube is None or md.dimension_in_cube(name, cube):
            return name
        fallback = fallback or name
    return fallback


def cube_dimensions(md: TenantMetadata, cube: str) -> list[str]:
    """Dimensions belonging to ``cube``, in outline order, excluding attributes."""
    c = md.cubes.get(cube)
    names = list(c.dimensions) if c and c.dimensions else list(md.dimensions)
    return [n for n in names
            if (d := md.dimensions.get(n)) is None or (d.type or "").lower() != "attribute"]


def resolve_member(md: TenantMetadata, dimension: str, *candidates: str | None) -> str | None:
    """Best real member name for any of ``candidates``, or None.

    Tried in strictly decreasing confidence so a weak match never beats a strong
    one for a later candidate: exact name, exact alias, vendor-prefixed variant
    ("Actual" -> "OEP_Actual"), de-prefixed variant, then a whole-word match.
    """
    pool = list(md.members.get(dimension, {}).values())
    names = [c for c in candidates if c]
    if not pool or not names:
        return None

    for name in names:
        if (hit := md.get_member(dimension, name)) is not None:
            return hit.name
    for name in names:
        for m in pool:
            if m.alias and m.alias.lower() == name.lower():
                return m.name
    for name in names:
        for prefix in VENDOR_PREFIXES:
            if (hit := md.get_member(dimension, prefix + name)) is not None:
                return hit.name
    for name in names:
        for prefix in VENDOR_PREFIXES:
            if name.lower().startswith(prefix.lower()):
                if (hit := md.get_member(dimension, name[len(prefix):])) is not None:
                    return hit.name
    # Whole-word, shortest-first: "Actual" should prefer "OEP_Actual" over
    # "OEP_Reporting Actual vs Forecast Range". Word boundaries also stop "Plan"
    # from matching "Planning Unit".
    for name in names:
        word = re.compile(rf"(?:^|[\s_]){re.escape(name)}(?:$|[\s_])", re.I)
        hits = sorted((m.name for m in pool if word.search(m.name)), key=len)
        if hits:
            return hits[0]
    return None


def roots(md: TenantMetadata, dimension: str) -> list[str]:
    """Top-of-outline members, preferring ones that actually have children.

    A dimension root is often a bare label like ``Scenario`` or ``Version`` that
    exists only to parent the real members — it resolves fine, which is what
    matters for a POV default.
    """
    pool = md.members.get(dimension, {})
    order = md.member_order.get(dimension, [])
    tops = [n for n in order
            if (m := pool.get(n.lower())) is not None
            and (not m.parent or m.parent.lower() not in pool)]
    parents = [n for n in tops if (m := pool.get(n.lower())) is not None and m.children]
    return parents or tops


def anchor_member(md: TenantMetadata, dimension: str, *preferred: str | None) -> str | None:
    """A member suitable as a hierarchy anchor for rows: preferred name, else root."""
    if (hit := resolve_member(md, dimension, *preferred)) is not None:
        return hit
    if (tops := roots(md, dimension)):
        return tops[0]
    order = md.member_order.get(dimension, [])
    return order[0] if order else None


def variable_for(md: TenantMetadata, dimension: str, scope: str) -> str | None:
    """Name of a ``scope`` ("user"/"substitution") variable bound to ``dimension``."""
    for var in md.variables.values():
        if var.dimension == dimension and (var.scope or "").lower() == scope.lower():
            return var.name
    return None


def pov_selection(md: TenantMetadata, dimension: str, *preferred: str | None) -> MemberSelection | None:
    """A single-member POV selection that is guaranteed to resolve.

    Prefers an explicit member, then the app's own substitution variable for the
    dimension (the EPM-idiomatic answer for Years/Period), then the root.
    """
    if (member := resolve_member(md, dimension, *preferred)) is not None:
        return MemberSelection(type="member", member=member)
    if (var := variable_for(md, dimension, "substitution")) is not None:
        return MemberSelection(type="substitutionVariable", variable=var)
    if (member := anchor_member(md, dimension)) is not None:
        return MemberSelection(type="member", member=member)
    return None


def page_selection(md: TenantMetadata, dimension: str) -> MemberSelection | None:
    """Pages selection for a dimension — a user variable if the app defines one.

    ``{CurrentEntity}`` is the Planning convention, but it only works if the
    tenant actually declares that user variable; otherwise we fall back to a real
    member so the page dropdown still has something valid in it.
    """
    if (var := variable_for(md, dimension, "user")) is not None:
        return MemberSelection(type="userVariable", variable=var)
    return pov_selection(md, dimension)


def period_columns(md: TenantMetadata, dimension: str) -> MemberSelection | None:
    """The dimension's base time span as a range, e.g. Jan:Dec — from the outline.

    Falls back to an explicit member list when the endpoints don't form a usable
    range (custom period dimensions, weekly calendars).
    """
    start = resolve_member(md, dimension, "Jan", "January")
    end = resolve_member(md, dimension, "Dec", "December")
    if start and end and md.range(dimension, start, end):
        return MemberSelection(type="range", start=start, end=end)

    leaves: list[str] = []
    for root in roots(md, dimension):
        leaves = [m for m in md.level_zero_descendants(dimension, root) if m]
        if len(leaves) > 1:
            break
    if len(leaves) > 1:
        first, last = leaves[0], leaves[-1]
        if md.range(dimension, first, last):
            return MemberSelection(type="range", start=first, end=last)
        return MemberSelection(type="memberList", members=leaves)
    if leaves:
        return MemberSelection(type="memberList", members=leaves)
    return None


def fill_pov(md: TenantMetadata, spec, cube: str) -> list[str]:
    """Park every unplaced cube dimension on the POV with a resolvable member.

    Without this the renderer silently defaults them to "a single member", which
    is both non-deterministic and invisible in the preview. Returns the dimension
    names added, for the inference list.
    """
    placed = {d.lower() for d in spec.dimensions_used()}
    added: list[str] = []
    for dim in cube_dimensions(md, cube):
        if dim.lower() in placed:
            continue
        if (sel := pov_selection(md, dim)) is None:
            continue
        spec.pov.append(AxisMember(dimension=dim, selection=sel))
        added.append(dim)
    return added
