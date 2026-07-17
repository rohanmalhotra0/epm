"""Deterministic report renderers: ReportSpecification -> HTML | CSV | JSON | MD.

The HTML renderer emits a self-contained, Oracle-EPM-styled document (inline CSS,
no external assets) that the artifact panel embeds and the download endpoint
serves as a standalone file. Smart formatting (colours, negative styling,
conditional rules) is applied via the shared preview model, so the on-screen
panel and the downloaded file always agree.
"""

from __future__ import annotations

import html
import io
import json
import zipfile
from xml.sax.saxutils import escape

from ..schemas.report_preview import ReportGridPreview, ReportPreview
from ..schemas.report_spec import ReportSpecification
from .metadata import TenantMetadata
from .packager import _FIXED_DT, _safe, sha256
from .report_preview import build_report_preview

RENDERER_VERSION = "1.0.0"


# --- HTML -------------------------------------------------------------------

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: #161616; background: #f4f4f4; }
.report { max-width: 1100px; margin: 0 auto; padding: 24px; }
.report h1 { font-size: 20px; margin: 0 0 4px; color: #0f62fe; }
.report .desc { color: #525252; margin: 0 0 16px; font-size: 13px; }
.report .meta { font-size: 12px; color: #6f6f6f; margin-bottom: 20px; }
.report .meta b { color: #393939; }
.grid { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 24px;
  overflow: hidden; }
.grid-title { font-size: 14px; font-weight: 600; padding: 12px 16px; border-bottom: 1px solid #e0e0e0;
  background: #f4f4f4; }
.pov { padding: 8px 16px; font-size: 12px; color: #525252; border-bottom: 1px solid #f0f0f0; }
.pov .chip { display: inline-block; background: #edf5ff; color: #0043ce; border-radius: 4px;
  padding: 2px 8px; margin: 2px 6px 2px 0; }
.tablewrap { overflow-x: auto; }
table.rpt { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
table.rpt th, table.rpt td { padding: 8px 12px; text-align: right; white-space: nowrap;
  border-bottom: 1px solid #f0f0f0; }
table.rpt thead th { background: #e8e8e8; color: #393939; font-weight: 600; position: sticky; top: 0; }
table.rpt th.rowhead, table.rpt td.rowhead { text-align: left; font-weight: 600; color: #161616;
  background: #fafafa; position: sticky; left: 0; }
table.rpt tbody tr:nth-child(even) td { background: #fbfbfb; }
table.rpt tfoot td { border-top: 2px solid #c6c6c6; font-weight: 600; background: #f4f4f4; }
.rules { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px 16px;
  font-size: 12px; color: #525252; }
.rules b { color: #393939; }
.chart { padding: 16px; }
.note { border-bottom: 1px dotted #8d8d8d; cursor: help; }
@media (prefers-color-scheme: dark) {
  body { color: #f4f4f4; background: #161616; }
  .grid, .rules { background: #262626; border-color: #393939; }
  .grid-title, table.rpt thead th, table.rpt tfoot td { background: #333; color: #f4f4f4; }
  table.rpt th.rowhead, table.rpt td.rowhead { background: #2a2a2a; color: #f4f4f4; }
  table.rpt tbody tr:nth-child(even) td { background: #202020; }
  .report h1 { color: #78a9ff; }
  .pov .chip { background: #001d6c; color: #a6c8ff; }
}
"""


def _cell_style(cell) -> str:
    styles = []
    if cell.color:
        styles.append(f"color:{cell.color}")
    if cell.background:
        styles.append(f"background:{cell.background}")
    if cell.bold:
        styles.append("font-weight:700")
    return f' style="{";".join(styles)}"' if styles else ""


def _cell_html(cell) -> str:
    inner = html.escape(cell.formatted)
    if cell.note:
        inner = f'<span class="note" title="{html.escape(cell.note)}">{inner}</span>'
    return f"<td{_cell_style(cell)}>{inner}</td>"


def _svg_bar_chart(grid: ReportGridPreview) -> str:
    """A tiny dependency-free bar chart of column totals (first row if no totals)."""
    labels = grid.column_labels
    if grid.column_totals:
        values = [c.value or 0 for c in grid.column_totals]
    elif grid.rows:
        values = [c.value or 0 for c in grid.rows[0].cells]
    else:
        return ""
    if not values:
        return ""
    w, h, pad = 640, 200, 30
    maxv = max((abs(v) for v in values), default=1) or 1
    bar_w = (w - 2 * pad) / max(len(values), 1)
    bars = []
    for i, v in enumerate(values):
        bh = (abs(v) / maxv) * (h - 2 * pad)
        x = pad + i * bar_w + bar_w * 0.15
        y = h - pad - bh
        color = "#da1e28" if v < 0 else "#0f62fe"
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.7:.1f}" height="{bh:.1f}" fill="{color}" rx="2"/>')
        lbl = escape(labels[i][:8]) if i < len(labels) else ""
        bars.append(f'<text x="{x + bar_w * 0.35:.1f}" y="{h - pad + 12:.1f}" font-size="9" text-anchor="middle" fill="#8d8d8d">{lbl}</text>')
    title = escape(grid.chart_title or grid.name)
    return (
        f'<div class="chart"><svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{title}">'
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#c6c6c6"/>'
        + "".join(bars)
        + "</svg></div>"
    )


def _grid_html(grid: ReportGridPreview) -> str:
    parts = [f'<div class="grid"><div class="grid-title">{html.escape(grid.name)}</div>']
    if grid.pov or grid.pages:
        chips = "".join(f'<span class="chip">{html.escape(p)}</span>' for p in (grid.pov + grid.pages))
        parts.append(f'<div class="pov">{chips}</div>')

    if grid.chart_type and grid.chart_type != "none":
        parts.append(_svg_bar_chart(grid))

    parts.append('<div class="tablewrap"><table class="rpt"><thead><tr><th class="rowhead"></th>')
    for c in grid.column_labels:
        parts.append(f"<th>{html.escape(c)}</th>")
    if grid.show_row_totals:
        parts.append("<th>Total</th>")
    parts.append("</tr></thead><tbody>")
    for row in grid.rows:
        parts.append(f'<tr><td class="rowhead">{html.escape(row.label)}</td>')
        parts.extend(_cell_html(cell) for cell in row.cells)
        if grid.show_row_totals and row.total is not None:
            parts.append(_cell_html(row.total))
        parts.append("</tr>")
    parts.append("</tbody>")
    if grid.show_column_totals and grid.column_totals:
        parts.append('<tfoot><tr><td class="rowhead">Total</td>')
        parts.extend(_cell_html(cell) for cell in grid.column_totals)
        if grid.show_row_totals:
            grand = sum((c.value or 0) for c in grid.column_totals)
            from ..schemas.report_spec import SmartFormat
            from .formatting import build_cell
            parts.append(_cell_html(build_cell(grand, SmartFormat())))
        parts.append("</tr></tfoot>")
    parts.append("</table></div></div>")
    return "".join(parts)


def render_report_html(spec: ReportSpecification, preview: ReportPreview) -> str:
    body = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(spec.name)}</title><style>{_CSS}</style></head><body>",
        '<div class="report">',
        f"<h1>{html.escape(spec.name)}</h1>",
    ]
    if spec.description:
        body.append(f'<p class="desc">{html.escape(spec.description)}</p>')
    body.append(
        f'<div class="meta"><b>Application:</b> {html.escape(spec.application)} &nbsp;·&nbsp; '
        f"<b>Cube:</b> {html.escape(spec.cube)} &nbsp;·&nbsp; <b>Type:</b> {html.escape(preview.report_type)}</div>"
    )
    for grid in preview.grids:
        body.append(_grid_html(grid))
    if preview.rule_associations:
        rules = ", ".join(html.escape(r) for r in preview.rule_associations)
        body.append(f'<div class="rules"><b>Business rules:</b> {rules}</div>')
    body.append("</div></body></html>")
    return "\n".join(body) + "\n"


# --- CSV / JSON / Markdown --------------------------------------------------


def render_report_csv(spec: ReportSpecification, preview: ReportPreview) -> str:
    import csv

    buf = io.StringIO()
    writer = csv.writer(buf)
    for grid in preview.grids:
        writer.writerow([f"# {spec.name} — {grid.name}"])
        if grid.pov or grid.pages:
            writer.writerow(["POV", *(grid.pov + grid.pages)])
        header = ["", *grid.column_labels]
        if grid.show_row_totals:
            header.append("Total")
        writer.writerow(header)
        for row in grid.rows:
            values = [c.value if c.value is not None else "" for c in row.cells]
            line = [row.label, *values]
            if grid.show_row_totals and row.total is not None:
                line.append(row.total.value)
            writer.writerow(line)
        if grid.show_column_totals and grid.column_totals:
            writer.writerow(["Total", *[c.value for c in grid.column_totals]])
        writer.writerow([])
    return buf.getvalue()


def render_report_json(spec: ReportSpecification) -> str:
    return json.dumps(spec.model_dump(by_alias=True, exclude_none=True), indent=2) + "\n"


def render_report_markdown(spec: ReportSpecification, preview: ReportPreview) -> str:
    lines = [f"# {spec.name}", ""]
    if spec.description:
        lines += [spec.description, ""]
    lines += [f"- **Application:** {spec.application}", f"- **Cube:** {spec.cube}",
              f"- **Type:** {preview.report_type}", ""]
    for grid in preview.grids:
        lines.append(f"## {grid.name}")
        if grid.pov or grid.pages:
            lines.append("_" + " · ".join(grid.pov + grid.pages) + "_")
        lines.append("")
        header = "| | " + " | ".join(grid.column_labels) + " |"
        sep = "|---|" + "|".join(["---:"] * len(grid.column_labels)) + "|"
        lines += [header, sep]
        for row in grid.rows:
            cells = " | ".join(c.formatted for c in row.cells)
            lines.append(f"| **{row.label}** | {cells} |")
        if grid.show_column_totals and grid.column_totals:
            totals = " | ".join(c.formatted for c in grid.column_totals)
            lines.append(f"| **Total** | {totals} |")
        lines.append("")
    if preview.rule_associations:
        lines += ["## Business Rules", ""]
        lines += [f"- {r}" for r in preview.rule_associations]
    return "\n".join(lines).rstrip() + "\n"


# --- download package -------------------------------------------------------


def build_report_package(spec: ReportSpecification, md: TenantMetadata, generated_at: str | None = None) -> dict:
    """Return {'zip','manifest','checksum','files','html','csv'} for downloads."""
    preview = build_report_preview(spec, md)
    html_doc = render_report_html(spec, preview)
    csv_doc = render_report_csv(spec, preview)
    json_doc = render_report_json(spec)
    md_doc = render_report_markdown(spec, preview)

    root = f"EPM_Wizard_Report_{_safe(spec.name)}"
    files: dict[str, str] = {
        f"{root}/{_safe(spec.name)}.html": html_doc,
        f"{root}/{_safe(spec.name)}.csv": csv_doc,
        f"{root}/{_safe(spec.name)}.json": json_doc,
        f"{root}/{_safe(spec.name)}.md": md_doc,
    }
    checksums = {name: sha256(text.encode("utf-8")) for name, text in sorted(files.items())}
    manifest = {
        "format": "epmwizard-report",
        "rendererVersion": RENDERER_VERSION,
        "specSchemaVersion": spec.schema_version,
        "artifactType": "report",
        "artifactName": spec.name,
        "application": spec.application,
        "cube": spec.cube,
        "reportType": preview.report_type,
        "files": sorted(files.keys()),
        "checksums": checksums,
    }
    if generated_at:
        manifest["generatedAt"] = generated_at
    files[f"{root}/manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files.keys()):
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DT)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])
    zip_bytes = buffer.getvalue()
    return {
        "zip": zip_bytes,
        "manifest": manifest,
        "checksum": sha256(zip_bytes),
        "files": files,
        "html": html_doc,
        "csv": csv_doc,
    }
