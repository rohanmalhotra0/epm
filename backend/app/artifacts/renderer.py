"""Deterministic artifact renderers (spec section 27).

FormSpecification -> XML | JSON | Markdown. Rendering is independent of the LLM
and reproducible: the same spec + renderer version yields byte-identical output.
XML is built with ElementTree (no string concatenation) and stable attribute
ordering.

Note (spec section 28): this is EPM Wizard's *normalised* form XML, not a claim
about Oracle's exact Cloud package layout. The parser round-trips it exactly; the
documented Migration workflow is what converts it for a live tenant.
"""

from __future__ import annotations

import json
from xml.etree import ElementTree as ET

from ..schemas.form_spec import FormSpecification, MemberSelection
from .metadata import TenantMetadata
from .preview import build_preview

RENDERER_VERSION = "1.0.0"
# `members` is intentionally omitted here — an explicit member list is rendered as
# child <member> elements (see render_xml), so member names containing a comma
# survive the render->parse round-trip losslessly.
_SEL_ATTR_ORDER = ["type", "member", "start", "end", "offsetStart", "offsetEnd",
                   "variable", "attribute", "namedSelection"]


def _selection_attrs(sel: MemberSelection) -> dict[str, str]:
    data = sel.model_dump(by_alias=True, exclude_none=True)
    attrs: dict[str, str] = {}
    for key in _SEL_ATTR_ORDER:
        if key in data:
            attrs[key] = str(data[key])
    return attrs


def render_xml(spec: FormSpecification) -> str:
    root = ET.Element("form")
    root.set("schemaVersion", spec.schema_version)
    root.set("name", spec.name)
    root.set("application", spec.application)
    root.set("cube", spec.cube)
    root.set("folder", spec.folder)
    root.set("rendererVersion", RENDERER_VERSION)

    if spec.description:
        ET.SubElement(root, "description").text = spec.description
    if spec.reference_template:
        ref = ET.SubElement(root, "reference")
        ref.set("type", spec.reference_template.type)
        ref.set("name", spec.reference_template.name)

    d = spec.display
    disp = ET.SubElement(root, "display")
    disp.set("useAliases", str(d.use_aliases).lower())
    disp.set("aliasTable", d.alias_table)
    disp.set("suppressMissingRows", str(d.suppress_missing_rows).lower())
    disp.set("suppressMissingColumns", str(d.suppress_missing_columns).lower())
    disp.set("readOnly", str(d.read_only).lower())
    if d.hidden_members:
        hidden = ET.SubElement(root, "hiddenMembers")
        for m in d.hidden_members:
            ET.SubElement(hidden, "member").text = m

    for kind, axis in (("pov", spec.pov), ("page", spec.pages), ("row", spec.rows), ("column", spec.columns)):
        axis_el = ET.SubElement(root, "axis")
        axis_el.set("kind", kind)
        for am in axis:
            dim_el = ET.SubElement(axis_el, "dimension")
            dim_el.set("name", am.dimension)
            dim_el.set("suppressMissing", str(am.suppress_missing).lower())
            sel_el = ET.SubElement(dim_el, "selection")
            for key, value in _selection_attrs(am.selection).items():
                sel_el.set(key, value)
            for member_name in am.selection.members or []:
                ET.SubElement(sel_el, "member").text = member_name

    if spec.business_rule_associations:
        rules_el = ET.SubElement(root, "businessRules")
        for assoc in spec.business_rule_associations:
            rule_el = ET.SubElement(rules_el, "rule")
            rule_el.set("name", assoc.rule_name)
            rule_el.set("type", assoc.rule_type)
            rule_el.set("association", assoc.association_type)
            for pm in assoc.prompt_mappings:
                pm_el = ET.SubElement(rule_el, "promptMapping")
                pm_el.set("prompt", pm.prompt_name)
                pm_el.set("source", pm.source)
                if pm.dimension:
                    pm_el.set("dimension", pm.dimension)
                if pm.value:
                    pm_el.set("value", pm.value)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def render_json(spec: FormSpecification) -> str:
    return json.dumps(spec.model_dump(by_alias=True, exclude_none=True), indent=2, sort_keys=False) + "\n"


def render_markdown(spec: FormSpecification, md: TenantMetadata | None = None) -> str:
    lines = [f"# {spec.name}", ""]
    if spec.description:
        lines += [spec.description, ""]
    lines += [
        f"- **Application:** {spec.application}",
        f"- **Cube:** {spec.cube}",
        f"- **Folder:** {spec.folder}",
    ]
    if spec.reference_template:
        lines.append(f"- **Reference:** {spec.reference_template.name}")
    lines.append("")

    def axis_block(title: str, axis) -> None:
        if not axis:
            return
        lines.append(f"## {title}")
        for am in axis:
            lines.append(f"- **{am.dimension}**: {am.selection.describe()}"
                         + ("  _(suppress missing)_" if am.suppress_missing else ""))
        lines.append("")

    axis_block("POV", spec.pov)
    axis_block("Pages", spec.pages)
    axis_block("Rows", spec.rows)
    axis_block("Columns", spec.columns)

    if spec.business_rule_associations:
        lines.append("## Business Rules")
        for a in spec.business_rule_associations:
            lines.append(f"- **{a.rule_name}** ({a.association_type})")
        lines.append("")

    if md is not None:
        preview = build_preview(spec, md)
        if preview.size_estimate:
            lines.append(f"_Estimated size: ~{preview.size_estimate.total_cells:,} cells._")
    return "\n".join(lines).rstrip() + "\n"
