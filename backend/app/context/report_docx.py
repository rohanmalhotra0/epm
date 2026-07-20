"""Human-readable Word (.docx) report of a learned context.

The ``.epwcontext`` package is a ZIP for re-import/sharing; this is the openable
counterpart — a formatted document of the application's cubes, dimensions,
member hierarchies, rules and variables that opens in Word / Pages / Google Docs.
"""

from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.shared import Inches, Pt
from sqlalchemy.orm import Session

from ..db.models import ContextVersion
from ..services import context_store

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _sorted_records(records: list, kind: str) -> list:
    return [r for r in records if r.kind == kind]


def _add_kv(doc, label: str, value: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(f"{label}: ")
    run.bold = True
    p.add_run(value)


def _add_table(doc, headers: list[str], rows: list[list[str]]):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
    return table


def _member_outline(doc, members: list) -> None:
    """Render one dimension's members as an indented hierarchy from parent links."""
    by_name = {m.name: m for m in members}
    children: dict[str | None, list] = {}
    for m in members:
        parent = m.parent if (m.parent and m.parent in by_name and m.parent != m.name) else None
        children.setdefault(parent, []).append(m)
    roots = children.get(None, [])

    def walk(node, depth: int) -> None:
        data = node.data or {}
        label = node.name
        alias = node.alias or data.get("alias")
        if alias and alias != node.name:
            label += f"  ({alias})"
        p = doc.add_paragraph(label, style="List Bullet")
        p.paragraph_format.left_indent = Inches(0.25 * depth)
        p.paragraph_format.space_after = Pt(0)
        for child in children.get(node.name, []):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)


def build_context_docx(session: Session, context_version_id: str) -> tuple[str, bytes]:
    cv = session.get(ContextVersion, context_version_id)
    if cv is None:
        raise KeyError("context version not found")
    records = context_store.get_records(session, context_version_id)
    counts = (cv.manifest or {}).get("counts", {})

    doc = Document()
    doc.add_heading(f"EPM Context Report — {cv.application}", level=0)
    _add_kv(doc, "Application", cv.application)
    _add_kv(doc, "Environment", (cv.manifest or {}).get("environmentClassification", "—"))
    _add_kv(doc, "Generated", (cv.manifest or {}).get("generatedAt", str(cv.created_at)))
    _add_kv(doc, "Context version", cv.label)

    # --- summary ---
    doc.add_heading("Summary", level=1)
    _add_table(doc, ["Category", "Count"],
               [[k.replace("_", " ").title(), str(v)] for k, v in counts.items()])

    # --- cubes ---
    cubes = _sorted_records(records, "cube")
    if cubes:
        doc.add_heading(f"Cubes ({len(cubes)})", level=1)
        rows = []
        for c in cubes:
            data = c.data or {}
            dims = data.get("dimensions") or []
            rows.append([c.name, data.get("type", ""), str(len(dims)), ", ".join(dims)])
        _add_table(doc, ["Cube", "Type", "# Dimensions", "Dimensions"], rows)

    # --- dimensions ---
    dims = _sorted_records(records, "dimension")
    if dims:
        doc.add_heading(f"Dimensions ({len(dims)})", level=1)
        rows = []
        for d in dims:
            data = d.data or {}
            rows.append([d.name, data.get("type", ""),
                         "Dense" if data.get("dense") else "Sparse",
                         ", ".join(data.get("cubes") or [])])
        _add_table(doc, ["Dimension", "Type", "Density", "Used in cubes"], rows)

    # --- members, grouped by dimension as an indented hierarchy ---
    members = _sorted_records(records, "member")
    if members:
        doc.add_heading(f"Members ({len(members)})", level=1)
        by_dim: dict[str, list] = {}
        for m in members:
            by_dim.setdefault(m.dimension or "—", []).append(m)
        for dim in sorted(by_dim):
            doc.add_heading(f"{dim} ({len(by_dim[dim])})", level=2)
            _member_outline(doc, by_dim[dim])
    else:
        doc.add_heading("Members", level=1)
        doc.add_paragraph(
            "No members were captured. Members require an EPM Automate metadata "
            "export or LCM snapshot; run a context refresh once that is configured."
        )

    # --- rules ---
    rules = _sorted_records(records, "rule")
    if rules:
        doc.add_heading(f"Business Rules ({len(rules)})", level=1)
        for r in rules:
            doc.add_paragraph(r.name, style="List Bullet")

    # --- variables ---
    variables = _sorted_records(records, "variable")
    if variables:
        doc.add_heading(f"Substitution & User Variables ({len(variables)})", level=1)
        rows = []
        for v in variables:
            data = v.data or {}
            rows.append([v.name, data.get("dimension") or "", str(data.get("value") or "")])
        _add_table(doc, ["Variable", "Dimension", "Value"], rows)

    buffer = BytesIO()
    doc.save(buffer)
    return f"{cv.label}.docx", buffer.getvalue()
