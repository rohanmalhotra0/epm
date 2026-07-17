"""In-memory tenant metadata used by the deterministic artifact engine.

Built from context records (persisted) or directly from connector output /
fixtures (tests). Provides the exact hierarchy operations the resolver needs.
Oracle identifiers and relationships are authoritative here — nothing is
approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas.context import (
    CubeRecord,
    DimensionRecord,
    FormRecord,
    MemberRecord,
    RuleRecord,
    VariableRecord,
)


@dataclass
class TenantMetadata:
    application: str
    cubes: dict[str, CubeRecord] = field(default_factory=dict)
    dimensions: dict[str, DimensionRecord] = field(default_factory=dict)
    # dimension -> {member_name_lower -> MemberRecord}
    members: dict[str, dict[str, MemberRecord]] = field(default_factory=dict)
    # dimension -> ordered list of member names (outline order)
    member_order: dict[str, list[str]] = field(default_factory=dict)
    variables: dict[str, VariableRecord] = field(default_factory=dict)
    forms: dict[str, FormRecord] = field(default_factory=dict)
    rules: dict[str, RuleRecord] = field(default_factory=dict)

    # --- lookups ---
    def has_cube(self, cube: str) -> bool:
        return cube in self.cubes

    def has_dimension(self, dimension: str) -> bool:
        return dimension in self.dimensions

    def dimension_in_cube(self, dimension: str, cube: str) -> bool:
        c = self.cubes.get(cube)
        return bool(c and dimension in c.dimensions)

    def get_member(self, dimension: str, name: str) -> MemberRecord | None:
        return self.members.get(dimension, {}).get(name.lower())

    def get_variable(self, name: str) -> VariableRecord | None:
        return self.variables.get(name.lower())

    # --- hierarchy ops ---
    def children(self, dimension: str, name: str) -> list[str]:
        m = self.get_member(dimension, name)
        return list(m.children) if m else []

    def descendants(self, dimension: str, name: str, inclusive: bool = False) -> list[str]:
        m = self.get_member(dimension, name)
        if not m:
            return []
        # depth-first, preserving stored child order, so descendants read top-down
        result: list[str] = []
        stack = list(reversed(m.children))
        while stack:
            child = stack.pop()
            result.append(child)
            cm = self.get_member(dimension, child)
            if cm:
                stack.extend(reversed(cm.children))
        return ([name] if inclusive else []) + result

    def level_zero_descendants(self, dimension: str, name: str) -> list[str]:
        return [d for d in self.descendants(dimension, name) if not self.children(dimension, d)]

    def ancestors(self, dimension: str, name: str, inclusive: bool = False) -> list[str]:
        out: list[str] = [name] if inclusive else []
        cur = self.get_member(dimension, name)
        while cur and cur.parent:
            out.append(cur.parent)
            cur = self.get_member(dimension, cur.parent)
        return out

    def siblings(self, dimension: str, name: str) -> list[str]:
        m = self.get_member(dimension, name)
        if not m or not m.parent:
            return [name]
        return self.children(dimension, m.parent)

    def range(self, dimension: str, start: str, end: str) -> list[str]:
        order = self.member_order.get(dimension, [])
        lower = {n.lower(): i for i, n in enumerate(order)}
        i, j = lower.get(start.lower()), lower.get(end.lower())
        if i is None or j is None:
            return []
        if i > j:
            i, j = j, i
        window = order[i : j + 1]
        # Oracle's ':' range returns members at the same level as the endpoints,
        # e.g. Jan:Dec yields the 12 months, not the quarter headers between them.
        start_member = self.get_member(dimension, start)
        if start_member is not None and start_member.level is not None:
            same_level = [
                n for n in window
                if (m := self.get_member(dimension, n)) is not None and m.level == start_member.level
            ]
            if same_level:
                return same_level
        return window

    def alias_of(self, dimension: str, name: str) -> str | None:
        m = self.get_member(dimension, name)
        return m.alias if m else None


def build_metadata(
    application: str,
    cubes: list[CubeRecord],
    dimensions: list[DimensionRecord],
    members: list[MemberRecord],
    variables: list[VariableRecord] | None = None,
    forms: list[FormRecord] | None = None,
    rules: list[RuleRecord] | None = None,
) -> TenantMetadata:
    md = TenantMetadata(application=application)
    md.cubes = {c.name: c for c in cubes}
    md.dimensions = {d.name: d for d in dimensions}
    for m in members:
        md.members.setdefault(m.dimension, {})[m.name.lower()] = m
        md.member_order.setdefault(m.dimension, []).append(m.name)
    md.variables = {v.name.lower(): v for v in (variables or [])}
    md.forms = {f.name.lower(): f for f in (forms or [])}
    md.rules = {r.name.lower(): r for r in (rules or [])}
    return md


async def build_metadata_from_connector(connector, application: str) -> TenantMetadata:
    cubes = await connector.list_cubes(application)
    dimensions = await connector.list_dimensions(application)
    members: list[MemberRecord] = []
    for d in dimensions:
        members.extend(await connector.list_members(application, d.name))
    variables = await connector.get_variables(application)
    forms = await connector.list_forms(application)
    rules = await connector.list_rules(application)
    return build_metadata(application, cubes, dimensions, members, variables, forms, rules)
