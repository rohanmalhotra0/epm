"""Regression tests for deterministic-engine edge cases found in the audit.

Each test pins a specific bug that previously produced a wrong/duplicate/looping
result in the engine that "owns" the deployable artifact:

* outline cycles used to hang the resolver (no visited set)
* shared/diamond hierarchies produced duplicate axis members
* levelZeroDescendants of a leaf returned [] (Oracle returns the member itself)
* relativeRange ignored its offsets and returned the whole dimension
* memberList kept duplicates
* member names containing a comma were split apart by the XML round-trip
"""

from __future__ import annotations

import pytest

from app.artifacts.metadata import build_metadata
from app.artifacts.parser import parse_xml
from app.artifacts.renderer import render_xml
from app.artifacts.resolver import ResolutionError, resolve_selection
from app.schemas.context import CubeRecord, DimensionRecord, MemberRecord
from app.schemas.form_spec import AxisMember, FormSpecification, MemberSelection


def _mem(name: str, dim: str, parent: str | None = None, children: tuple[str, ...] = ()) -> MemberRecord:
    return MemberRecord(name=name, dimension=dim, application="APP", parent=parent, children=list(children))


def _md(dim: str, members: list[MemberRecord]):
    return build_metadata(
        "APP",
        [CubeRecord(name="C", application="APP", dimensions=[dim])],
        [DimensionRecord(name=dim, application="APP")],
        members,
    )


def test_diamond_hierarchy_deduplicates_descendants():
    md = _md("A", [
        _mem("Tot", "A", children=("X", "Y")),
        _mem("X", "A", "Tot", ("Shared",)),
        _mem("Y", "A", "Tot", ("Shared",)),
        _mem("Shared", "A"),
    ])
    assert md.descendants("A", "Tot") == ["X", "Shared", "Y"]  # Shared appears once


def test_outline_cycle_does_not_hang():
    md = _md("D", [_mem("A", "D", "B", ("B",)), _mem("B", "D", "A", ("A",))])
    # Before the visited-set guard these looped forever; now they terminate.
    assert set(md.descendants("D", "A")) == {"A", "B"}
    assert md.ancestors("D", "A") == ["B"]


def test_level_zero_descendants_of_a_leaf_is_the_member():
    md = _md("A", [_mem("Tot", "A", children=("Leaf",)), _mem("Leaf", "A", "Tot")])
    assert md.level_zero_descendants("A", "Leaf") == ["Leaf"]


def test_relative_range_windows_by_offsets():
    md = _md("P", [_mem(m, "P") for m in ("Jan", "Feb", "Mar", "Apr")])
    r = resolve_selection(md, "P", MemberSelection(type="relativeRange", member="Mar", offset_start=-1, offset_end=1))
    assert r.members == ["Feb", "Mar", "Apr"]


def test_relative_range_without_anchor_is_refused():
    md = _md("P", [_mem(m, "P") for m in ("Jan", "Feb", "Mar")])
    with pytest.raises(ResolutionError):
        resolve_selection(md, "P", MemberSelection(type="relativeRange", offset_start=-1, offset_end=1))


def test_member_list_deduplicates():
    md = _md("P", [_mem(m, "P") for m in ("Jan", "Feb")])
    r = resolve_selection(md, "P", MemberSelection(type="memberList", members=["Jan", "Jan", "Feb"]))
    assert r.members == ["Jan", "Feb"]


def test_xml_round_trip_preserves_member_names_with_commas():
    spec = FormSpecification(
        name="T", application="APP", cube="C",
        rows=[AxisMember(dimension="A",
                         selection=MemberSelection(type="memberList", members=["Sales, Net", "COGS"]))],
        columns=[AxisMember(dimension="P", selection=MemberSelection(type="member", member="Jan"))],
    )
    back = parse_xml(render_xml(spec))
    assert back.rows[0].selection.members == ["Sales, Net", "COGS"]
