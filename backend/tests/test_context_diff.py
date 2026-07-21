"""Record-level context diff tests (spec section 18)."""

from __future__ import annotations

import copy

from app.connector import DemoConnector
from app.context import build_context, diff_context_records
from app.services import context_store, projects


def test_diff_context_records_added_removed_changed():
    a = [
        {"kind": "member", "name": "Salaries", "dimension": "Account", "cube": None,
         "data": {"alias": "Base Salaries", "parent": "Total Payroll"}},
        {"kind": "member", "name": "Wages", "dimension": "Account", "cube": None,
         "data": {"alias": "Hourly", "parent": "Total Payroll"}},
        {"kind": "form", "name": "Old Form", "dimension": None, "cube": "OEP_FS",
         "data": {"folder": "X"}},
    ]
    b = [
        # Salaries: alias changed
        {"kind": "member", "name": "Salaries", "dimension": "Account", "cube": None,
         "data": {"alias": "Renamed", "parent": "Total Payroll"}},
        # Wages: unchanged
        {"kind": "member", "name": "Wages", "dimension": "Account", "cube": None,
         "data": {"alias": "Hourly", "parent": "Total Payroll"}},
        # New Form added; Old Form removed
        {"kind": "form", "name": "New Form", "dimension": None, "cube": "OEP_WFP",
         "data": {"folder": "Y"}},
    ]
    d = diff_context_records(a, b)

    members = d["member"]
    assert members["added"] == [] and members["removed"] == []
    assert members["changed"] == [{
        "name": "Salaries", "dimension": "Account",
        "before": {"alias": "Base Salaries"}, "after": {"alias": "Renamed"},
    }]

    forms = d["form"]
    assert forms["added"] == [{"name": "New Form", "dimension": None, "cube": "OEP_WFP"}]
    assert forms["removed"] == [{"name": "Old Form", "dimension": None, "cube": "OEP_FS"}]
    assert forms["changed"] == []


def test_shared_members_are_not_collapsed():
    # A shared member (same name+dimension under two parents) is two rows; the
    # diff must not collapse them and silently drop a real removal.
    a = [
        {"kind": "member", "name": "IT", "dimension": "Entity", "cube": None,
         "parent": "Corporate", "data": {"parent": "Corporate"}},
        {"kind": "member", "name": "IT", "dimension": "Entity", "cube": None,
         "parent": "Regions", "data": {"parent": "Regions"}},
    ]
    b = [
        {"kind": "member", "name": "IT", "dimension": "Entity", "cube": None,
         "parent": "Corporate", "data": {"parent": "Corporate"}},
    ]
    result = diff_context_records(a, b)
    member = result["member"]
    # the shared 'Regions' instance is a genuine removal, not a spurious change
    assert {"name": "IT", "dimension": "Entity", "cube": None} in member["removed"]
    assert member["changed"] == []
    assert member["added"] == []


def test_diff_context_records_caps_with_overflow_counts():
    a: list[dict] = []
    b = [{"kind": "member", "name": f"M{i:03d}", "dimension": "Account", "cube": None, "data": {}}
         for i in range(150)]
    d = diff_context_records(a, b, cap=100)
    m = d["member"]
    assert len(m["added"]) == 100
    assert m["addedTruncated"] == 50
    # deterministic sorted order — first entry is the lowest name
    assert m["added"][0]["name"] == "M000"
    assert m["removedTruncated"] == 0 and m["changedTruncated"] == 0


async def test_diff_records_store_and_route(session, client):
    proj = projects.get_default_project(session)
    bundle = await build_context(DemoConnector(), "MCWPCF", mode="quick")

    cv_a = context_store.persist_context(
        session, proj.id, bundle.application, bundle.mode, bundle.label,
        bundle.manifest.model_dump(by_alias=True), bundle.counts, bundle.records)

    # Build a second version: drop one record (removed), add one (added),
    # mutate one member's data (changed).
    records_b = copy.deepcopy(bundle.records)
    removed_rec = next(r for r in records_b if r["kind"] == "member")
    records_b = [r for r in records_b if r is not removed_rec]
    changed_rec = next(r for r in records_b if r["kind"] == "member")
    changed_rec["data"] = {**(changed_rec["data"] or {}), "alias": "DIFFERENT_ALIAS"}
    records_b.append({
        "kind": "member", "name": "BrandNewMember", "dimension": "Account",
        "cube": None, "alias": None, "parent": None, "application": "MCWPCF",
        "search_text": "brandnewmember", "data": {"alias": "Fresh"},
    })
    cv_b = context_store.persist_context(
        session, proj.id, bundle.application, bundle.mode, bundle.label + "_v2",
        bundle.manifest.model_dump(by_alias=True), bundle.counts, records_b)
    session.commit()  # make both versions visible to the route's own DB session

    payload = context_store.diff_records(session, cv_a.id, cv_b.id)
    assert payload["versionA"]["id"] == cv_a.id
    assert payload["versionB"]["label"] == bundle.label + "_v2"
    member = payload["kinds"]["member"]
    assert any(x["name"] == "BrandNewMember" for x in member["added"])
    assert any(x["name"] == removed_rec["name"] for x in member["removed"])
    assert any(x["name"] == changed_rec["name"] for x in member["changed"])

    # Route: bare-dict return, mirrors store payload.
    res = client.get(f"/api/contexts/{cv_a.id}/diff", params={"against": cv_b.id})
    assert res.status_code == 200
    body = res.json()
    assert body["versionA"]["id"] == cv_a.id
    assert "member" in body["kinds"]

    # 404 when a version is unknown.
    assert client.get(f"/api/contexts/{cv_a.id}/diff", params={"against": "nope"}).status_code == 404
