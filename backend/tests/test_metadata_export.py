"""Parser tests for the EPM Automate metadata-export member import."""

from __future__ import annotations

import zipfile

from app.connector.metadata_export import parse_metadata_export

# One CSV per dimension; the first column is named after the dimension and holds
# the member, matching Oracle's Export Metadata format. "Line Item" exercises a
# dimension name with a space; "Smart Lists" is a non-dimension artifact.
_ENTITY_CSV = (
    "Entity,Parent,Alias: Default,Data Storage,Data Type\n"
    "Total Entity,,Total Entity,Never Share,Unspecified\n"
    "US,Total Entity,United States,Store,Unspecified\n"
    "US East,US,,Store,Unspecified\n"
)
_LINE_ITEM_CSV = (
    "Line Item,Parent,Alias: Default\n"
    "Total,,All Lines\n"
    "Revenue,Total,\n"
)
_SMARTLIST_CSV = "Name,Entries\nStatuses,Open;Closed\n"


def _build_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Entity.csv", _ENTITY_CSV)
        zf.writestr("Line Item.csv", _LINE_ITEM_CSV)
        zf.writestr("Smart Lists.csv", _SMARTLIST_CSV)
    return path


def test_parses_members_with_fields(tmp_path):
    zip_path = _build_zip(tmp_path / "export.zip")
    members = parse_metadata_export(zip_path, "APP", dimensions={"Entity", "Line Item"})
    by_name = {m.name: m for m in members}
    assert set(by_name) == {"Total Entity", "US", "US East", "Total", "Revenue"}  # Smart Lists excluded
    us = by_name["US"]
    assert us.dimension == "Entity" and us.parent == "Total Entity"
    assert us.alias == "United States" and us.storage == "Store"
    assert by_name["Total Entity"].alias == "Total Entity" and by_name["Total Entity"].parent is None


def test_derives_child_hierarchy(tmp_path):
    zip_path = _build_zip(tmp_path / "export.zip")
    members = parse_metadata_export(zip_path, "APP", dimensions={"Entity", "Line Item"})
    by_name = {m.name: m for m in members}
    # children are derived from parent pointers so descendants/levelZero resolve
    assert by_name["Total Entity"].children == ["US"]
    assert by_name["US"].children == ["US East"]
    assert by_name["US East"].children == []


def test_dimension_name_with_space_and_filter(tmp_path):
    zip_path = _build_zip(tmp_path / "export.zip")
    # no filter -> the non-dimension "Smart Lists" file is also parsed
    all_dims = {m.dimension for m in parse_metadata_export(zip_path, "APP")}
    assert "Smart Lists" in all_dims
    # filtered -> only the known dimensions are kept
    filtered = {m.dimension for m in parse_metadata_export(zip_path, "APP", dimensions={"Entity", "Line Item"})}
    assert filtered == {"Entity", "Line Item"}
