"""Deterministic artifact engine tests (spec sections 4, 21, 26, 27)."""

from __future__ import annotations

import pytest

from app.artifacts import (
    build_form_package,
    build_metadata_from_connector,
    parse_xml,
    render_xml,
    resolve_selection,
    validate_form,
)
from app.connector import DemoConnector
from app.schemas.form_spec import FormSpecification, MemberSelection



async def _md():
    return await build_metadata_from_connector(DemoConnector(), "MCWPCF")


def _spec(**overrides) -> FormSpecification:
    base = dict(
        name="Test Form", application="MCWPCF", cube="OEP_FS",
        rows=[{"dimension": "Account", "selection": {"type": "levelZeroDescendants", "member": "Total Payroll"}, "suppressMissing": True}],
        columns=[{"dimension": "Period", "selection": {"type": "range", "start": "Jan", "end": "Dec"}}],
        pov=[{"dimension": "Scenario", "selection": {"type": "member", "member": "Actual"}}],
    )
    base.update(overrides)
    return FormSpecification.model_validate(base)


async def test_level_zero_descendants():
    md = await _md()
    r = resolve_selection(md, "Account", MemberSelection(type="levelZeroDescendants", member="Total Payroll"))
    assert r.members == ["Salaries", "Wages", "Overtime", "Bonus", "Commissions", "Benefits", "Payroll Taxes"]


async def test_range_is_level_aware():
    md = await _md()
    months = resolve_selection(md, "Period", MemberSelection(type="range", start="Jan", end="Dec")).members
    assert months == ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


async def test_children_and_descendants():
    md = await _md()
    kids = resolve_selection(md, "Account", MemberSelection(type="children", member="Total Payroll")).members
    assert "Salaries" in kids and "Total Payroll" not in kids
    idesc = resolve_selection(md, "Account", MemberSelection(type="inclusiveDescendants", member="Total Payroll")).members
    assert idesc[0] == "Total Payroll"


async def test_validation_passes_for_valid_form():
    md = await _md()
    report = validate_form(_spec(), md)
    assert report.valid and not report.blocking


async def test_validation_flags_unknown_member_with_candidates():
    md = await _md()
    bad = _spec(rows=[{"dimension": "Account", "selection": {"type": "descendants", "member": "Total Payrol"}}])
    report = validate_form(bad, md)
    assert report.blocking
    issue = next(i for i in report.issues if i.code == "MEMBER_NOT_FOUND")
    assert "Total Payroll" in issue.candidates


async def test_validation_flags_wrong_cube():
    md = await _md()
    bad = _spec(cube="NOPE")
    report = validate_form(bad, md)
    assert any(i.code == "CUBE_NOT_FOUND" for i in report.issues)


async def test_xml_roundtrip_is_lossless():
    spec = _spec()
    xml = render_xml(spec)
    reparsed = parse_xml(xml)
    assert reparsed.model_dump(by_alias=True) == spec.model_dump(by_alias=True)


async def test_package_is_deterministic():
    spec = _spec()
    a = build_form_package(spec)
    b = build_form_package(spec)
    assert a["checksum"] == b["checksum"]
    assert a["zip"] == b["zip"]
    assert "manifest.json" in "".join(a["files"].keys())


def test_form_requires_rows_and_columns():
    with pytest.raises(Exception):
        FormSpecification.model_validate({"name": "x", "application": "a", "cube": "c", "rows": [],
                                          "columns": [{"dimension": "P", "selection": {"type": "member", "member": "Jan"}}]})


def test_dimension_cannot_be_on_two_axes():
    with pytest.raises(Exception):
        FormSpecification.model_validate({
            "name": "x", "application": "a", "cube": "c",
            "rows": [{"dimension": "Account", "selection": {"type": "member", "member": "A"}}],
            "columns": [{"dimension": "Account", "selection": {"type": "member", "member": "B"}}],
        })
