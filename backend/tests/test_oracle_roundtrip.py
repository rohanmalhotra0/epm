"""Explicit native render <-> parse round-trip guard (spec sections 27, 28).

This is the honest, tenant-free half of the Oracle deployment workflow
(docs/ORACLE_ARTIFACT_RESEARCH.md, steps 5-6): EPM Wizard's *normalized* form
XML renders, parses, and re-renders byte-identically, and its package builds
reproducibly. It makes NO claim about Oracle's real Migration package layout.
"""

from __future__ import annotations

from app.artifacts import build_form_package, parse_xml, render_xml
from app.schemas.form_spec import FormSpecification


def _spec() -> FormSpecification:
    return FormSpecification.model_validate(dict(
        name="Round Trip Form", application="MCWPCF", cube="OEP_FS",
        description="Guard against render/parse drift.",
        rows=[{"dimension": "Account",
               "selection": {"type": "levelZeroDescendants", "member": "Total Payroll"},
               "suppressMissing": True}],
        columns=[{"dimension": "Period", "selection": {"type": "range", "start": "Jan", "end": "Dec"}}],
        pov=[{"dimension": "Scenario", "selection": {"type": "member", "member": "Actual"}}],
    ))


def test_render_parse_render_is_byte_identical():
    """render_xml -> parse_xml -> render_xml must reproduce the exact bytes."""
    spec = _spec()
    xml_once = render_xml(spec)
    reparsed = parse_xml(xml_once)
    xml_twice = render_xml(reparsed)
    assert xml_twice == xml_once
    # And the parsed spec is structurally identical to the original.
    assert reparsed.model_dump(by_alias=True) == spec.model_dump(by_alias=True)


def test_form_package_is_reproducible_byte_for_byte():
    """build_form_package twice yields identical zip bytes and checksum."""
    spec = _spec()
    a = build_form_package(spec)
    b = build_form_package(spec)
    assert a["zip"] == b["zip"]
    assert a["checksum"] == b["checksum"]
    # Re-rendering the parsed spec then repackaging is still identical.
    c = build_form_package(parse_xml(render_xml(spec)))
    assert c["zip"] == a["zip"]
