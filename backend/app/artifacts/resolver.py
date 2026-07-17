"""Deterministic member-selection resolution (spec sections 4, 19, 21).

Turns a MemberSelection into an exact, ordered list of member names using the
tenant outline. Oracle identifiers/relationships are authoritative — the model
never substitutes a similar member.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas.common import SelectionType
from ..schemas.form_spec import MemberSelection
from .metadata import TenantMetadata


class ResolutionError(Exception):
    def __init__(self, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.candidates = candidates or []


@dataclass
class Resolution:
    members: list[str]
    method: str
    truncated: bool = False


def resolve_selection(
    md: TenantMetadata, dimension: str, selection: MemberSelection, limit: int = 5000
) -> Resolution:
    t = SelectionType(selection.type)

    def require(name: str) -> None:
        if md.get_member(dimension, name) is None:
            # offer near matches as candidates
            cands = _candidates(md, dimension, name)
            raise ResolutionError(
                f"Member '{name}' was not found in dimension '{dimension}'.", cands
            )

    if t is SelectionType.member:
        require(selection.member)
        return Resolution([_canonical(md, dimension, selection.member)], "member")

    if t is SelectionType.member_list:
        out = []
        for m in selection.members or []:
            require(m)
            out.append(_canonical(md, dimension, m))
        return Resolution(out, "memberList")

    if t in (SelectionType.children, SelectionType.inclusive_children):
        require(selection.member)
        kids = md.children(dimension, selection.member)
        if t is SelectionType.inclusive_children:
            kids = [_canonical(md, dimension, selection.member), *kids]
        return _cap(kids, "children", limit)

    if t in (SelectionType.descendants, SelectionType.inclusive_descendants):
        require(selection.member)
        desc = md.descendants(dimension, selection.member, inclusive=(t is SelectionType.inclusive_descendants))
        return _cap(desc, "descendants", limit)

    if t is SelectionType.level_zero_descendants:
        require(selection.member)
        return _cap(md.level_zero_descendants(dimension, selection.member), "levelZeroDescendants", limit)

    if t in (SelectionType.ancestors, SelectionType.inclusive_ancestors):
        require(selection.member)
        anc = md.ancestors(dimension, selection.member, inclusive=(t is SelectionType.inclusive_ancestors))
        return _cap(anc, "ancestors", limit)

    if t is SelectionType.siblings:
        require(selection.member)
        return _cap(md.siblings(dimension, selection.member), "siblings", limit)

    if t is SelectionType.range:
        members = md.range(dimension, selection.start, selection.end)
        if not members:
            raise ResolutionError(
                f"Range {selection.start}:{selection.end} does not resolve in dimension '{dimension}'."
            )
        return _cap(members, "range", limit)

    if t is SelectionType.relative_range:
        # relative to current period is tenant-specific; resolve against outline order
        order = md.member_order.get(dimension, [])
        return _cap(order, "relativeRange", limit)

    if t in (SelectionType.substitution_variable, SelectionType.user_variable):
        var = md.get_variable(selection.variable)
        if var is None:
            raise ResolutionError(f"Variable '{selection.variable}' was not found.")
        value = var.value or ""
        # a variable may resolve to a member; keep the raw value if not found
        member = md.get_member(dimension, value)
        return Resolution([member.name if member else value], "variable")

    if t is SelectionType.attribute:
        return Resolution([f"@Attribute({selection.attribute})"], "attribute")

    if t is SelectionType.named_selection:
        return Resolution([f"@Named({selection.named_selection})"], "namedSelection")

    if t in (SelectionType.pov_reference, SelectionType.page_reference):
        return Resolution([f"@{t.value}"], t.value)

    raise ResolutionError(f"Unsupported selection type '{t.value}'.")


def _canonical(md: TenantMetadata, dimension: str, name: str) -> str:
    m = md.get_member(dimension, name)
    return m.name if m else name


def _cap(members: list[str], method: str, limit: int) -> Resolution:
    if len(members) > limit:
        return Resolution(members[:limit], method, truncated=True)
    return Resolution(members, method)


def _candidates(md: TenantMetadata, dimension: str, name: str, limit: int = 6) -> list[str]:
    q = name.lower()
    out = []
    for member in md.members.get(dimension, {}).values():
        if q in member.name.lower() or (member.alias and q in member.alias.lower()):
            out.append(member.name)
        if len(out) >= limit:
            break
    return out
