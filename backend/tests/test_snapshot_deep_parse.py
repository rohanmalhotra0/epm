"""LCM snapshot deep-parse tests: smart lists, data maps, valid intersections,
and dashboards.

These four categories are optional in an Oracle Migration snapshot (the shipped
"Artifact Snapshot" fixture carries none of them — see the absence-tolerance
test in test_snapshot_context.py). When present, each file is deep-parsed into a
structured record; a malformed file degrades to a name-only record plus an
issue, and an absent folder yields no records and an ``unavailable`` section.
The synthetic-zip builder pattern is borrowed from test_snapshot_context.py.
"""

from __future__ import annotations

import io
import zipfile

from app.context import analyze_snapshot, merge_snapshot_into_context
from app.rag import build_chunks, retrieve_grounding
from app.services import context_store
from app.services import projects as projects_svc

_APP = "ACME_PLN"
_HP = f"HP-{_APP}"
_DIMS = f"{_HP}/resource/Global Artifacts/Common Dimensions/Standard Dimensions"
_GLOBAL = f"{_HP}/resource/Global Artifacts"


# --- synthetic snapshot builder (pattern from test_snapshot_context) -----------


def _dim_csv(dimension: str, rows: list[str], dim_type: str = "None") -> str:
    header_block = (
        "#!-- HEADERBLOCK DIMENSION XML\n"
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        "<DIMENSIONS>\n"
        f' <Dimension name="{dimension}" density="Sparse" dimensionType="{dim_type}">\n'
        " </Dimension>\n"
        "</DIMENSIONS>\n"
        "#--!\n"
    )
    header = (f"{dimension}, Parent, Alias: Default, Data Storage, Formula, Data Type, UDA,"
              " Smart List, Description, Aggregation (Plan1), Data Storage (Plan1)")
    return "﻿" + header_block + header + "\n" + "\n".join(rows) + "\n"


# Deliberately varied root/element tag casing to prove local-tag matching.
_SMART_LIST = """<?xml version="1.0" encoding="UTF-8" ?>
<smartlist name="Status">
 <entry name="0"><label>Open</label><value>0</value></entry>
 <entry name="1"><label>Closed</label><value>1</value></entry>
</smartlist>
"""

# Alternate spelling: <SmartList> root + <smartListEntry> children + attributes.
_SMART_LIST_ALT = """<?xml version="1.0" encoding="UTF-8" ?>
<SmartList name="Priority">
 <smartListEntry name="lo" label="Low" value="1"/>
 <smartListEntry name="hi" label="High" value="9"/>
</SmartList>
"""

# Data map with child <source>/<target> cube references.
_DATA_MAP = """<?xml version="1.0" encoding="UTF-8" ?>
<dataMap name="ActualsToPlan">
 <source cube="OEP_FS"/>
 <target cube="OEP_PLAN"/>
</dataMap>
"""

# Data map with cubes carried as root attributes instead.
_DATA_MAP_ATTR = """<?xml version="1.0" encoding="UTF-8" ?>
<DataMap name="PushToReporting" sourceCube="OEP_FS" targetCube="OEP_REP"/>
"""

_VALID_INTERSECTION = """<?xml version="1.0" encoding="UTF-8" ?>
<validIntersection name="EntityAccount">
 <dimension name="Entity"/>
 <dimension name="Account"/>
</validIntersection>
"""

_DASHBOARD = """<?xml version="1.0" encoding="UTF-8" ?>
<dashboard name="Exec Summary">
 <object type="form" name="Rolling Forecast"/>
 <form name="Cash Detail"/>
</dashboard>
"""

_CUBE_DASHBOARD = """<?xml version="1.0" encoding="UTF-8" ?>
<Dashboard name="Cash Cockpit">
 <formName>Cash Detail</formName>
</Dashboard>
"""


def _base_files() -> dict[str, str]:
    return {
        f"{_DIMS}/Account.csv": _dim_csv("Account", [
            "Account,,,,,,,,,,",
            "Salaries,Account,Base Salaries,store data,,currency,,,,+,store data",
        ], dim_type="Account"),
    }


def _all_categories() -> dict[str, str]:
    files = _base_files()
    files[f"{_GLOBAL}/Smart Lists/Status.xml"] = _SMART_LIST
    files[f"{_GLOBAL}/Data Maps/ActualsToPlan.xml"] = _DATA_MAP
    files[f"{_GLOBAL}/Valid Intersections/EntityAccount.xml"] = _VALID_INTERSECTION
    files[f"{_GLOBAL}/Dashboards/Exec Summary.xml"] = _DASHBOARD
    files[f"{_HP}/resource/Cube/Plan1/Dashboards/Cash Cockpit.xml"] = _CUBE_DASHBOARD
    return files


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, text in sorted(files.items()):
            zf.writestr(path, text.encode("utf-8"))
    return buf.getvalue()


def _by_kind(bundle, kind: str) -> dict[str, dict]:
    return {r["name"]: r for r in bundle.records if r["kind"] == kind}


# --- deep parsing ---------------------------------------------------------------


def test_all_categories_deep_parse_records_counts_and_sections():
    bundle = analyze_snapshot(_zip_bytes(_all_categories()))
    a = bundle.analysis
    assert a.issues == []
    assert a.counts["smartLists"] == 1
    assert a.counts["dataMaps"] == 1
    assert a.counts["validIntersections"] == 1
    assert a.counts["dashboards"] == 2  # one global + one per-cube

    sl = _by_kind(bundle, "smartList")["Status"]["data"]
    assert sl["application"] == _APP and sl["source"] == "snapshot"
    assert sl["entries"] == [
        {"name": "0", "label": "Open", "value": "0"},
        {"name": "1", "label": "Closed", "value": "1"},
    ]

    dm = _by_kind(bundle, "dataMap")["ActualsToPlan"]["data"]
    assert dm["sourceCube"] == "OEP_FS" and dm["targetCube"] == "OEP_PLAN"

    vi = _by_kind(bundle, "validIntersection")["EntityAccount"]["data"]
    assert vi["dimensions"] == ["Entity", "Account"]

    dash = _by_kind(bundle, "dashboard")
    assert dash["Exec Summary"]["data"]["forms"] == ["Rolling Forecast", "Cash Detail"]
    assert dash["Exec Summary"]["data"].get("cube") is None
    assert dash["Cash Cockpit"]["data"]["cube"] == "Plan1"
    assert dash["Cash Cockpit"]["data"]["forms"] == ["Cash Detail"]

    sections = {s.name: s for s in bundle.sections}
    for name in ("Smart Lists", "Data Maps", "Valid Intersections", "Dashboards"):
        assert sections[name].status == "complete", name
    assert sections["Dashboards"].count == 2

    # every deep-parsed record is provenance-tagged
    assert all(r["data"].get("source") == "snapshot"
               for r in bundle.records
               if r["kind"] in ("smartList", "dataMap", "validIntersection", "dashboard"))


def test_varied_tag_casing_and_attribute_forms_are_tolerated():
    files = _base_files()
    files[f"{_GLOBAL}/Smart Lists/Priority.xml"] = _SMART_LIST_ALT
    files[f"{_GLOBAL}/Data Maps/PushToReporting.xml"] = _DATA_MAP_ATTR
    bundle = analyze_snapshot(_zip_bytes(files))
    assert bundle.analysis.issues == []

    sl = _by_kind(bundle, "smartList")["Priority"]["data"]
    assert sl["entries"] == [
        {"name": "lo", "label": "Low", "value": "1"},
        {"name": "hi", "label": "High", "value": "9"},
    ]
    dm = _by_kind(bundle, "dataMap")["PushToReporting"]["data"]
    assert dm["sourceCube"] == "OEP_FS" and dm["targetCube"] == "OEP_REP"


def test_malformed_file_degrades_to_name_only_plus_issue():
    files = _base_files()
    files[f"{_GLOBAL}/Smart Lists/Good.xml"] = _SMART_LIST
    files[f"{_GLOBAL}/Smart Lists/Broken.xml"] = "<smartlist name='Broken'"  # truncated
    bundle = analyze_snapshot(_zip_bytes(files))

    assert any("Broken.xml" in i for i in bundle.analysis.issues)
    smart = _by_kind(bundle, "smartList")
    assert set(smart) == {"Good", "Broken"}
    assert smart["Good"]["data"]["entries"]  # deep-parsed
    assert "entries" not in smart["Broken"]["data"]  # name-only fallback
    assert smart["Broken"]["data"] == {"name": "Broken", "application": _APP, "source": "snapshot"}

    # at least one file deep-parsed -> section stays complete
    assert {s.name: s.status for s in bundle.sections}["Smart Lists"] == "complete"
    assert bundle.analysis.counts["smartLists"] == 2  # total records, incl. the stub


def test_all_malformed_marks_section_derived():
    files = _base_files()
    files[f"{_GLOBAL}/Valid Intersections/Broken.xml"] = "<validIntersection name='x'"
    bundle = analyze_snapshot(_zip_bytes(files))
    assert any("Broken.xml" in i for i in bundle.analysis.issues)
    sections = {s.name: s.status for s in bundle.sections}
    assert sections["Valid Intersections"] == "derived"  # present, names only
    assert _by_kind(bundle, "validIntersection")["Broken"]["data"].get("dimensions") is None


def test_absent_folders_yield_no_records_and_unavailable_sections():
    bundle = analyze_snapshot(_zip_bytes(_base_files()))
    for kind in ("smartList", "dataMap", "validIntersection", "dashboard"):
        assert not [r for r in bundle.records if r["kind"] == kind]
    counts = bundle.analysis.counts
    for ckey in ("smartLists", "dataMaps", "validIntersections", "dashboards"):
        assert ckey not in counts
    sections = {s.name: s.status for s in bundle.sections}
    for name in ("Smart Lists", "Data Maps", "Valid Intersections", "Dashboards"):
        assert sections[name] == "unavailable", name


def test_summary_mentions_deep_parsed_categories():
    from app.context import summarize_snapshot
    bundle = analyze_snapshot(_zip_bytes(_all_categories()))
    text = summarize_snapshot(bundle.analysis)
    assert "smart lists" in text and "data maps" in text
    assert "valid intersections" in text and "dashboards" in text


# --- chunker + RAG --------------------------------------------------------------


def test_deep_parsed_kinds_produce_searchable_chunks(session):
    proj = projects_svc.create_project(session, "DeepChunks")
    bundle = analyze_snapshot(_zip_bytes(_all_categories()))
    cv = merge_snapshot_into_context(session, proj.id, bundle, standalone=True)
    session.flush()

    chunks = {(c.kind, c.name): c for c in build_chunks(context_store.get_records(session, cv.id))}
    assert "Open" in chunks[("smartList", "Status")].text  # entry labels searchable
    assert "OEP_FS" in chunks[("dataMap", "ActualsToPlan")].text
    assert "Entity" in chunks[("validIntersection", "EntityAccount")].text
    assert "Rolling Forecast" in chunks[("dashboard", "Exec Summary")].text


async def test_rag_surfaces_smart_list_by_entry_content(session):
    proj = projects_svc.create_project(session, "DeepRag")
    bundle = analyze_snapshot(_zip_bytes(_all_categories()))
    cv = merge_snapshot_into_context(session, proj.id, bundle, standalone=True)
    session.flush()

    out = await retrieve_grounding(session, cv.id, "Closed Open status smart list",
                                   kinds=["smartList"], k=3)
    assert out and out[0].kind == "smartList" and out[0].name == "Status"
