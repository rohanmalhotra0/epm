"""Parse an Oracle Planning "Export Metadata" archive into MemberRecords.

Member/dimension enumeration is not exposed by the Planning REST API, so members
are obtained by running a saved Export Metadata job via EPM Automate and parsing
the resulting ZIP. The archive contains one CSV per dimension (``<Dimension>.csv``)
whose first column holds the member name, followed by ``Parent``, ``Alias:
Default``, ``Data Storage``, ``Data Type``, ``Formula`` (column set varies by app).

Parsing is defensive: unknown columns are ignored, the child hierarchy is derived
from parent pointers (so descendants/levelZeroDescendants resolve), and a file
that doesn't correspond to a known dimension is skipped.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from ..schemas.context import MemberRecord

# Header aliases (matched case-insensitively) -> the field we map them to.
_PARENT_HEADERS = ("parent",)
_ALIAS_HEADERS = ("alias: default", "alias:default", "default alias", "alias")
_STORAGE_HEADERS = ("data storage", "storage")
_DATA_TYPE_HEADERS = ("data type",)
_FORMULA_HEADERS = ("formula",)


def _pick(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {h.lower().strip(): h for h in headers}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def _strip_lcm_header(text: str) -> str:
    """LCM snapshot dimension files prefix the member CSV with an XML metadata
    block ('#!-- HEADERBLOCK DIMENSION XML' … '</DIMENSIONS>'). Drop it so the CSV
    parser sees the header row first. Plain Export-Metadata files pass through."""
    if "#!-- HEADERBLOCK" not in text[:256]:
        return text
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("</DIMENSIONS"):
            start = i + 1
            break
    # Skip the marker/comment/blank lines (e.g. '#--!') that separate the XML
    # header block from the CSV, so the first returned line is the CSV header.
    while start < len(lines) and (not lines[start].strip() or lines[start].lstrip().startswith("#")):
        start += 1
    return "\n".join(lines[start:])


def _parse_csv(text: str, dimension: str, application: str) -> list[MemberRecord]:
    reader = csv.reader(io.StringIO(_strip_lcm_header(text)))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    if not headers:
        return []
    # The member column is the one named after the dimension, else "Member", else col 0.
    member_col = 0
    for i, h in enumerate(headers):
        if h.lower() in (dimension.lower(), "member"):
            member_col = i
            break
    parent_h = _pick(headers, _PARENT_HEADERS)
    alias_h = _pick(headers, _ALIAS_HEADERS)
    storage_h = _pick(headers, _STORAGE_HEADERS)
    dtype_h = _pick(headers, _DATA_TYPE_HEADERS)
    formula_h = _pick(headers, _FORMULA_HEADERS)
    idx = {h: i for i, h in enumerate(headers)}

    def cell(row: list[str], header: str | None) -> str | None:
        if header is None:
            return None
        i = idx[header]
        val = row[i].strip() if i < len(row) else ""
        return val or None

    records: list[MemberRecord] = []
    for row in rows[1:]:
        if member_col >= len(row):
            continue
        name = row[member_col].strip()
        if not name:
            continue
        records.append(MemberRecord(
            name=name, dimension=dimension, application=application,
            parent=cell(row, parent_h), alias=cell(row, alias_h),
            storage=cell(row, storage_h), data_type=cell(row, dtype_h),
            formula=cell(row, formula_h),
        ))
    return _link_children(records)


def _link_children(records: list[MemberRecord]) -> list[MemberRecord]:
    """Populate each member's ``children`` from parent pointers, preserving order."""
    by_name: dict[str, MemberRecord] = {r.name: r for r in records}
    for r in records:
        if r.parent and r.parent in by_name and r.parent != r.name:
            by_name[r.parent].children.append(r.name)
    return records


def parse_metadata_export(
    zip_path: str | Path, application: str, dimensions: set[str] | None = None
) -> list[MemberRecord]:
    """Parse every dimension CSV in the export ZIP into MemberRecords.

    ``dimensions`` (case-insensitive names) restricts parsing to known dimensions
    so non-dimension artifacts in the archive (smart lists, exchange rates, …) are
    ignored. If omitted, every ``*.csv`` entry is treated as a dimension.
    """
    wanted = {d.lower() for d in dimensions} if dimensions else None
    members: list[MemberRecord] = []
    with zipfile.ZipFile(zip_path) as zf:
        for entry in zf.namelist():
            if not entry.lower().endswith(".csv"):
                continue
            stem = Path(entry).stem
            if wanted is not None and stem.lower() not in wanted:
                continue
            try:
                text = zf.read(entry).decode("utf-8-sig", "replace")
            except KeyError:
                continue
            members.extend(_parse_csv(text, stem, application))
    return members


def parse_lcm_snapshot(
    zip_path: str | Path, application: str, dimensions: set[str] | None = None
) -> list[MemberRecord]:
    """Extract dimension members from an LCM application-snapshot ZIP.

    Planning stores each dimension under a '…/Dimensions/<Dim>.csv' path (an XML
    header block followed by the standard member CSV). Only entries on a
    ``Dimensions`` path whose stem is a known dimension are parsed, so the many
    other artifacts in a snapshot (security, FDMEE, data maps) are ignored.
    """
    wanted = {d.lower() for d in dimensions} if dimensions else None
    members: list[MemberRecord] = []
    with zipfile.ZipFile(zip_path) as zf:
        for entry in zf.namelist():
            low = entry.lower()
            if not low.endswith(".csv") or "dimension" not in low:
                continue
            stem = Path(entry).stem
            if wanted is not None and stem.lower() not in wanted:
                continue
            text = zf.read(entry).decode("utf-8-sig", "replace")
            members.extend(_parse_csv(text, stem, application))
    return members
