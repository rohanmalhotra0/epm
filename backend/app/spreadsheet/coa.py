"""Turn a chart-of-accounts sheet into a validated HierarchyParse.

Supports both real-world shapes:

* parent/child format — a member column plus a parent column (+ optional alias
  and data-storage columns);
* level-column format — Level 1..Level N columns, either indent style (one
  value per row) or full-path style (ancestors repeated on each row).

Member names are validated against the connector identifier rules (shell
metacharacters, traversal, length). Invalid names, duplicates, orphans and
cycles are reported as issues — never silently fixed.
"""

from __future__ import annotations

import re

from ..connector.errors import InvalidArgument
from ..connector.validation import validate_identifier
from .models import ColumnInfo, ColumnRole, HierarchyParse, ParsedMember

_LEVEL_NUM_RE = re.compile(r"(\d+)\s*$")
_GENERIC_MEMBER_HEADERS = {"member", "member name", "child", "child member", "name", "dimension member"}
_GENERIC_SHEET_NAMES = re.compile(r"(?i)^sheet\s*\d*$")
_STORAGE_HEADERS = {"data storage", "storage", "data storage (account)"}
MAX_ISSUES = 50


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def _guess_dimension(member_header: str | None, sheet_name: str) -> str:
    if member_header and member_header.strip().lower() not in _GENERIC_MEMBER_HEADERS:
        return member_header.strip()
    if sheet_name and not _GENERIC_SHEET_NAMES.match(sheet_name.strip()):
        return sheet_name.strip()
    return "Dimension"


def _validated_name(raw: str, row_no: int, field: str, issues: list[str]) -> str | None:
    try:
        return validate_identifier(raw, field)
    except InvalidArgument as exc:
        if len(issues) < MAX_ISSUES:
            issues.append(f"row {row_no}: {exc}")
        return None


def build_hierarchy(
    columns: list[ColumnInfo],
    body: list[list[object]],
    sheet_name: str = "",
    header_rows: int = 1,
) -> HierarchyParse:
    issues: list[str] = []
    members: list[ParsedMember] = []
    seen: dict[str, ParsedMember] = {}

    member_col = next((c for c in columns if c.role == ColumnRole.member), None)
    parent_col = next((c for c in columns if c.role == ColumnRole.parent), None)
    alias_col = next((c for c in columns if c.role == ColumnRole.alias), None)
    storage_col = next((c for c in columns if c.header.strip().lower() in _STORAGE_HEADERS), None)
    level_cols = sorted(
        (c for c in columns if c.role == ColumnRole.level),
        key=lambda c: int(_LEVEL_NUM_RE.search(c.header).group(1)) if _LEVEL_NUM_RE.search(c.header) else c.index,
    )

    def cell(row: list[object], col: ColumnInfo | None) -> str:
        if col is None or col.index >= len(row):
            return ""
        return _text(row[col.index])

    def add(name: str, parent: str | None, alias: str | None, storage: str | None,
            row_no: int, path_style: bool = False) -> None:
        existing = seen.get(name)
        if existing is not None:
            # full-path level format legitimately repeats ancestors with the same parent
            if not (path_style and existing.parent == parent):
                if len(issues) < MAX_ISSUES:
                    issues.append(f"duplicate member '{name}' at row {row_no} ignored")
            if alias and not existing.alias:
                existing.alias = alias
            return
        member = ParsedMember(name=name, parent=parent, alias=alias or None, storage=storage or None)
        seen[name] = member
        members.append(member)

    if member_col is not None and parent_col is not None:
        for i, row in enumerate(body):
            row_no = header_rows + i + 1
            raw = cell(row, member_col)
            if not raw:
                continue
            name = _validated_name(raw, row_no, "member name", issues)
            if name is None:
                continue
            parent_raw = cell(row, parent_col)
            parent: str | None = None
            if parent_raw:
                parent = _validated_name(parent_raw, row_no, f"parent of '{name}'", issues)
                if parent is None and len(issues) <= MAX_ISSUES:
                    issues.append(f"row {row_no}: member '{name}' kept as a root because its parent was rejected")
            add(name, parent, cell(row, alias_col) or None, cell(row, storage_col) or None, row_no)
    elif len(level_cols) >= 2:
        stack: dict[int, str] = {}  # level position (0-based) -> last member seen
        for i, row in enumerate(body):
            row_no = header_rows + i + 1
            filled = [(pos, cell(row, col)) for pos, col in enumerate(level_cols) if cell(row, col)]
            if not filled:
                continue
            deepest_pos = filled[-1][0]
            prev_in_row: str | None = None
            for pos, raw in filled:
                name = _validated_name(raw, row_no, "member name", issues)
                if name is None:
                    continue
                if pos == 0:
                    parent = None
                else:
                    parent = prev_in_row if prev_in_row is not None else stack.get(pos - 1)
                    if parent is None and len(issues) < MAX_ISSUES:
                        issues.append(
                            f"row {row_no}: '{name}' appears at level {pos + 1} with no ancestor above it"
                        )
                alias = cell(row, alias_col) or None if pos == deepest_pos else None
                storage = cell(row, storage_col) or None if pos == deepest_pos else None
                add(name, parent, alias, storage, row_no, path_style=len(filled) > 1)
                stack[pos] = name
                for deeper in [k for k in stack if k > pos]:
                    del stack[deeper]
                prev_in_row = name
    else:
        issues.append("no member+parent columns and fewer than two level columns; nothing to parse")

    # orphans: parent named but never defined as a member
    names = set(seen)
    for m in members:
        if m.parent and m.parent not in names and len(issues) < MAX_ISSUES:
            issues.append(f"member '{m.name}' references unknown parent '{m.parent}'")

    # cycles: walk parent chains
    reported: set[str] = set()
    for m in members:
        path: list[str] = []
        current: ParsedMember | None = m
        while current is not None and current.parent:
            if current.name in path:
                cycle = path[path.index(current.name):] + [current.name]
                key = "->".join(sorted(set(cycle)))
                if key not in reported:
                    reported.add(key)
                    issues.append(f"cycle detected: {' -> '.join(cycle)}")
                break
            path.append(current.name)
            current = seen.get(current.parent)

    return HierarchyParse(
        dimension_guess=_guess_dimension(member_col.header if member_col else None, sheet_name),
        members=members,
        root_count=sum(1 for m in members if not m.parent),
        issues=issues,
    )
