"""Deterministic Calculation Manager rule rendering + import package.

Completes the rule-creation story the same way forms are handled: a saved rule
draft (RuleSpecification + proposed script) is rendered into the exact HBRRepo
XML shape the snapshot parser reads (``app.context.snapshot._parse_rule_file``)
and wrapped in a reproducible Migration-style zip. The user imports the package
manually via Migration (LCM); nothing here ever deploys anything.

Determinism: no wall-clock anywhere, ElementTree with stable ordering, fixed
zip timestamps and sorted entries — identical inputs yield byte-identical zips.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from xml.etree import ElementTree as ET

from ..schemas.rule_spec import RuleSpecification
from .packager import _FIXED_DT, _safe, sha256

# Characters outside the XML 1.0 legal set (nulls and most C0 control chars).
# ElementTree serialises these verbatim, producing bytes no conformant parser
# can read back — so a script body or spec field carrying them would break the
# "valid, round-trippable XML" contract. Strip them before serialisation.
_ILLEGAL_XML = re.compile(  # XML 1.0 forbids these: C0 controls except tab/LF/CR + FFFE/FFFF
    "[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _xml_safe(value: str) -> str:
    return _ILLEGAL_XML.sub("", value or "")


RULE_RENDERER_VERSION = "1.0.0"
GENERATOR = f"epm-wizard-rule-packager/{RULE_RENDERER_VERSION}"
PACKAGE_ROOT = "CALC-Calculation Manager"

_SCRIPT_TYPES = ("groovy", "calcscript")
# Placeholder swapped for a CDATA section after serialisation — ElementTree has
# no native CDATA support and calcscript bodies must not be entity-escaped.
_CDATA_TOKEN = "__EPM_WIZARD_CDATA_BODY__"


def _prop(parent: ET.Element, name: str, text: str) -> None:
    el = ET.SubElement(parent, "property")
    el.set("name", name)
    el.text = _xml_safe(text)


def _cdata(body: str) -> str:
    # "]]>" inside the body would close the section early; split it across two.
    return "<![CDATA[" + body.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def render_rule_xml(spec: RuleSpecification, script: str, script_type: str = "groovy") -> str:
    """Render one rule draft as Calc Manager HBRRepo XML (single line, like the
    extension-less files under CALC-.../resource/Planning/<App>/<Cube>/Rules/).

    calcscript bodies are emitted in CDATA; groovy bodies as escaped text.
    Runtime prompts become member variables (usage="const") plus matching
    variable_reference rows, mirroring real snapshot rule files.
    """
    if script_type not in _SCRIPT_TYPES:
        raise ValueError(f"script_type must be one of {_SCRIPT_TYPES}, got {script_type!r}")

    root = ET.Element("HBRRepo")
    variables = ET.SubElement(root, "variables")
    for i, prompt in enumerate(spec.runtime_prompts, start=1):
        var = ET.SubElement(variables, "variable")
        var.set("name", _xml_safe(prompt.name))
        var.set("type", "member")
        var.set("usage", "const")
        var.set("id", str(i))
        var.set("product", "Planning")
        _prop(var, "application", spec.application)
        _prop(var, "dimensionInputMode", "type")
        if prompt.dimension:
            _prop(var, "dimensionType", prompt.dimension)
        _prop(var, "prompt_text", prompt.prompt_text or prompt.name)
        _prop(var, "scope", "rule")
        value = ET.SubElement(var, "value")
        if prompt.default_value:
            value.text = _xml_safe(prompt.default_value)

    ET.SubElement(root, "rulesets")
    rules = ET.SubElement(root, "rules")
    rule = ET.SubElement(rules, "rule")
    rule.set("id", "1")
    rule.set("name", _xml_safe(spec.name))
    rule.set("product", "Planning")
    _prop(rule, "application", spec.application)
    _prop(rule, "plantype", spec.cube)
    if spec.runtime_prompts:
        refs = ET.SubElement(rule, "variable_references")
        for i, prompt in enumerate(spec.runtime_prompts, start=1):
            ref = ET.SubElement(refs, "variable_reference")
            ref.set("name", _xml_safe(prompt.name))
            ref.set("id", str(i))
            _prop(ref, "application", spec.application)
            _prop(ref, "hidden", "false")
            _prop(ref, "rule_name", spec.name)
            _prop(ref, "seq", str(i))
            _prop(ref, "type", "3")
            _prop(ref, "useAsOverrideValue", "false")
    script_el = ET.SubElement(rule, "script")
    script_el.set("type", script_type)
    script_el.text = _CDATA_TOKEN if script_type == "calcscript" else _xml_safe(script)
    ET.SubElement(root, "templates")

    body = ET.tostring(root, encoding="unicode")
    if script_type == "calcscript":
        body = body.replace(_CDATA_TOKEN, _cdata(_xml_safe(script)), 1)
    return "<?xml version = '1.0' encoding = 'UTF-8'?>\n" + body


_CONTROL_RE = re.compile("[\x00-\x1f\x7f]")


def _path_component(name: str) -> str:
    """A zip path segment: keep the real name (spaces included, like snapshot
    rule files) but never let it introduce extra path levels — and never let a
    control/null byte truncate the entry name (zip readers stop at a NUL, which
    would silently blank the leaf and make the archive non-deterministic)."""
    cleaned = _CONTROL_RE.sub("", name or "")
    cleaned = cleaned.replace("/", "_").replace("\\", "_").strip().strip(".")
    return cleaned or "_"


def build_rule_package(
    spec: RuleSpecification, script: str, script_type: str = "groovy"
) -> tuple[str, bytes]:
    """Return (filename, zip bytes) for a Migration-importable Calc Manager
    package. Reproducible: byte-identical for identical inputs."""
    rule_xml = render_rule_xml(spec, script, script_type)
    rule_path = "/".join((
        PACKAGE_ROOT, "resource", "Planning",
        _path_component(spec.application), _path_component(spec.cube),
        "Rules", _path_component(spec.name),
    ))
    files: dict[str, str] = {rule_path: rule_xml}

    checksums = {name: sha256(text.encode("utf-8")) for name, text in sorted(files.items())}
    manifest = {
        "generator": GENERATOR,
        "checksums": checksums,
        "ruleName": spec.name,
        "application": spec.application,
        "cube": spec.cube,
        "scriptType": script_type,
    }
    files["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files.keys()):
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DT)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])
    return f"{_safe(spec.name)}_calcrules.zip", buffer.getvalue()
