"""Adversarial fuzz tests for the record-level context diff + context store.

Contract under test (spec section 18):
  * ``engine.diff_context_records`` never crashes on any input, always returns
    the documented per-kind shape, caps correctly, is deterministic (byte
    identical run to run), and is linear — no O(n^2) blow-up on 10k records.
  * ``context_store.diff_records`` is safe against self-diff, missing versions,
    cross-project versions, and empty/huge record sets.
  * ``context_store.build_tenant_metadata`` never crashes on hostile record
    data — bad records are skipped, not fatal.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import time

from app.connector import DemoConnector
from app.context import build_context
from app.context.engine import diff_context_records
from app.services import context_store, projects


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _rec(kind="member", name="M", dimension="Account", cube=None, parent=None,
         alias=None, application="APP", data=None, search_text=None):
    return {
        "kind": kind, "name": name, "dimension": dimension, "cube": cube,
        "alias": alias, "parent": parent, "application": application,
        "search_text": search_text or (name or "").lower(),
        "data": {} if data is None else data,
    }


def _shape_ok(kind_result: dict) -> None:
    """Every per-kind block must carry exactly the documented keys/types."""
    assert set(kind_result) == {
        "added", "removed", "changed",
        "addedTruncated", "removedTruncated", "changedTruncated",
    }
    for lst in ("added", "removed", "changed"):
        assert isinstance(kind_result[lst], list)
    for n in ("addedTruncated", "removedTruncated", "changedTruncated"):
        assert isinstance(kind_result[n], int) and kind_result[n] >= 0


# --------------------------------------------------------------------------- #
# diff_context_records — structural edge cases
# --------------------------------------------------------------------------- #
def test_two_empty_lists():
    assert diff_context_records([], []) == {}


def test_one_empty_side():
    b = [_rec(name="A"), _rec(name="B")]
    d = diff_context_records([], b)
    assert [e["name"] for e in d["member"]["added"]] == ["A", "B"]
    assert d["member"]["removed"] == [] and d["member"]["changed"] == []
    _shape_ok(d["member"])

    d2 = diff_context_records(b, [])
    assert [e["name"] for e in d2["member"]["removed"]] == ["A", "B"]
    assert d2["member"]["added"] == []


def test_identical_self_diff_is_all_empty():
    # A kind bucket is only created when there is an add/remove/change, so a
    # perfectly identical self-diff collapses to an empty mapping.
    recs = [_rec(name=f"M{i}", data={"alias": f"a{i}"}) for i in range(50)]
    d = diff_context_records(recs, copy.deepcopy(recs))
    assert d == {}


def test_records_missing_all_keys_do_not_crash():
    a = [{}, {"name": "x"}, {"kind": "member"}]
    b = [{}, {"data": {"k": 1}}]
    d = diff_context_records(a, b)  # must not raise
    for kind in d:
        _shape_ok(d[kind])


def test_none_data_on_both_sides():
    a = [_rec(name="X", data=None)]
    a[0]["data"] = None
    b = [{"kind": "member", "name": "X", "dimension": "Account", "cube": None, "data": None}]
    d = diff_context_records(a, b)
    # None data on both -> treated as empty -> no changed
    assert d.get("member", {}).get("changed", []) == []


def test_non_dict_data_never_crashes():
    for bad in ([1, 2, 3], "a string", 42, 3.14, True, ("t",)):
        a = [{"kind": "member", "name": "X", "dimension": "A", "cube": None, "data": bad}]
        b = [{"kind": "member", "name": "X", "dimension": "A", "cube": None, "data": {"alias": "z"}}]
        d = diff_context_records(a, b)  # must not raise
        _shape_ok(d["member"])


def test_shared_members_not_collapsed():
    # Same name+dimension under two parents => two distinct rows.
    a = [_rec(name="IT", dimension="Entity", parent="Corporate", data={"parent": "Corporate"}),
         _rec(name="IT", dimension="Entity", parent="Regions", data={"parent": "Regions"})]
    b = [_rec(name="IT", dimension="Entity", parent="Corporate", data={"parent": "Corporate"})]
    d = diff_context_records(a, b)
    assert {"name": "IT", "dimension": "Entity", "cube": None} in d["member"]["removed"]
    assert d["member"]["changed"] == [] and d["member"]["added"] == []


def test_true_duplicate_keys_collapse_by_design():
    # Identical identity tuple => same logical row; the map dedupes. Document it.
    a = [_rec(name="D", parent="P", data={"alias": "1"}),
         _rec(name="D", parent="P", data={"alias": "2"})]
    d = diff_context_records(a, [])
    assert len(d["member"]["removed"]) == 1  # collapsed, not two


def test_only_data_differs_vs_only_identity_differs():
    # only data differs -> changed
    a = [_rec(name="M", data={"alias": "old"})]
    b = [_rec(name="M", data={"alias": "new"})]
    d = diff_context_records(a, b)
    assert d["member"]["changed"] == [
        {"name": "M", "dimension": "Account", "before": {"alias": "old"}, "after": {"alias": "new"}}
    ]
    assert d["member"]["added"] == [] and d["member"]["removed"] == []

    # only identity differs (parent) -> add + remove, no changed
    a2 = [_rec(name="M", parent="P1", data={"alias": "x"})]
    b2 = [_rec(name="M", parent="P2", data={"alias": "x"})]
    d2 = diff_context_records(a2, b2)
    assert d2["member"]["changed"] == []
    assert len(d2["member"]["added"]) == 1 and len(d2["member"]["removed"]) == 1


def test_changed_reports_only_differing_data_keys():
    a = [_rec(name="M", data={"alias": "a", "parent": "P", "formula": "F"})]
    b = [_rec(name="M", data={"alias": "a", "parent": "Q", "formula": "F", "extra": 1})]
    ch = diff_context_records(a, b)["member"]["changed"][0]
    assert ch["before"] == {"extra": None, "parent": "P"}
    assert ch["after"] == {"extra": 1, "parent": "Q"}


def test_unicode_and_none_names():
    a = [_rec(name=None, dimension=None), _rec(name="café", dimension="Δim"),
         _rec(name="日本語", dimension="Account")]
    b = [_rec(name="café", dimension="Δim", data={"alias": "changed"})]
    d = diff_context_records(a, b)  # must not raise on None/unicode
    for kind in d:
        _shape_ok(d[kind])
    assert d["member"]["changed"][0]["name"] == "café"


def test_unknown_and_mixed_kinds_bucketed():
    a = [_rec(kind="wombat", name="W"), _rec(kind="member", name="M"),
         _rec(kind=None, name="none-kind")]
    d = diff_context_records(a, [])
    assert "wombat" in d and "member" in d and "" in d  # None kind -> "" bucket
    for kind in d:
        _shape_ok(d[kind])


def test_cube_parent_key_collisions_are_distinct():
    # same name+dimension, differing cube => distinct rows, both survive.
    a = [_rec(kind="form", name="F", dimension=None, cube="OEP_FS", data={}),
         _rec(kind="form", name="F", dimension=None, cube="OEP_WFP", data={})]
    d = diff_context_records(a, [])
    cubes = sorted(e["cube"] for e in d["form"]["removed"])
    assert cubes == ["OEP_FS", "OEP_WFP"]


# --------------------------------------------------------------------------- #
# cap behaviour
# --------------------------------------------------------------------------- #
def test_cap_zero():
    b = [_rec(name=f"M{i:03d}") for i in range(10)]
    d = diff_context_records([], b, cap=0)
    assert d["member"]["added"] == []
    assert d["member"]["addedTruncated"] == 10


def test_negative_cap_clamped_not_tail_sliced():
    b = [_rec(name=f"M{i:03d}") for i in range(10)]
    d = diff_context_records([], b, cap=-5)
    # BUG-FIX: negative cap must behave as 0, not slice the tail nor inflate overflow.
    assert d["member"]["added"] == []
    assert d["member"]["addedTruncated"] == 10


def test_huge_cap_no_truncation():
    b = [_rec(name=f"M{i:03d}") for i in range(120)]
    d = diff_context_records([], b, cap=10**9)
    assert len(d["member"]["added"]) == 120
    assert d["member"]["addedTruncated"] == 0


def test_cap_exact_boundary():
    b = [_rec(name=f"M{i:03d}") for i in range(100)]
    d = diff_context_records([], b, cap=100)
    assert len(d["member"]["added"]) == 100 and d["member"]["addedTruncated"] == 0


# --------------------------------------------------------------------------- #
# scale + determinism
# --------------------------------------------------------------------------- #
def test_huge_lists_linear_and_capped():
    n = 12_000
    a = [_rec(name=f"A{i:06d}") for i in range(n)]              # all removed
    b = [_rec(name=f"B{i:06d}") for i in range(n)]              # all added
    # plus n common members, half of them changed
    common_a = [_rec(name=f"C{i:06d}", data={"alias": "x"}) for i in range(n)]
    common_b = [_rec(name=f"C{i:06d}", data={"alias": "y" if i % 2 else "x"}) for i in range(n)]
    t0 = time.perf_counter()
    d = diff_context_records(a + common_a, b + common_b, cap=100)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"diff too slow ({elapsed:.2f}s) — possible O(n^2)"
    m = d["member"]
    assert len(m["added"]) == 100 and m["addedTruncated"] == n - 100
    assert len(m["removed"]) == 100 and m["removedTruncated"] == n - 100
    assert len(m["changed"]) == 100 and m["changedTruncated"] == (n // 2) - 100


def test_output_sorted_by_full_key():
    # deterministic order = sorted by (name, dimension, parent, cube)
    b = [_rec(kind="form", name="F", dimension=None, cube=f"C{i:02d}") for i in range(30)]
    d = diff_context_records([], b)
    cubes = [e["cube"] for e in d["form"]["added"]]
    assert cubes == sorted(cubes)


def test_determinism_across_hash_seeds(tmp_path):
    # Colliding (name, dimension) rows differing only by cube must serialise
    # identically regardless of PYTHONHASHSEED (set iteration order).
    script = tmp_path / "det.py"
    script.write_text(
        "import json\n"
        "from app.context.engine import diff_context_records\n"
        "b=[{'kind':'form','name':'F','dimension':None,'cube':'C%02d'%i,'data':{}} for i in range(40)]\n"
        "print(json.dumps(diff_context_records([], b), sort_keys=True))\n"
    )
    outs = set()
    for seed in ("0", "1", "77", "12345"):
        r = subprocess.run([sys.executable, str(script)], capture_output=True,
                           text=True, env={"PYTHONHASHSEED": seed, "PATH": ""},
                           cwd=".")
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout)
    assert len(outs) == 1, "diff output varies with PYTHONHASHSEED — not deterministic"


def test_repeated_calls_byte_identical():
    a = [_rec(name=f"M{i}", cube=f"C{i%3}", data={"alias": str(i)}) for i in range(200)]
    b = [_rec(name=f"M{i}", cube=f"C{i%3}", data={"alias": str(i * 2)}) for i in range(200)]
    first = json.dumps(diff_context_records(a, b), sort_keys=True)
    for _ in range(5):
        assert json.dumps(diff_context_records(a, b), sort_keys=True) == first


# --------------------------------------------------------------------------- #
# context_store.diff_records (needs a DB session)
# --------------------------------------------------------------------------- #
def _persist(session, project_id, records, label):
    return context_store.persist_context(
        session, project_id, "APP", "quick", label,
        manifest={}, counts={}, records=records, activate=False)


async def test_store_self_diff_is_empty(session):
    proj = projects.get_default_project(session)
    bundle = await build_context(DemoConnector(), "MCWPCF", mode="quick")
    cv = context_store.persist_context(
        session, proj.id, bundle.application, bundle.mode, bundle.label,
        bundle.manifest.model_dump(by_alias=True), bundle.counts, bundle.records,
        activate=False)
    session.commit()
    payload = context_store.diff_records(session, cv.id, cv.id)
    for kind, block in payload["kinds"].items():
        assert block["added"] == [] and block["removed"] == [] and block["changed"] == []


async def test_store_diff_against_nonexistent_version(session):
    proj = projects.get_default_project(session)
    cv = _persist(session, proj.id, [_rec(name="Solo")], "solo")
    session.commit()
    payload = context_store.diff_records(session, cv.id, "does-not-exist")
    assert payload["versionB"]["id"] == "does-not-exist"
    assert payload["versionB"]["label"] is None
    # everything in A shows as removed; nothing crashes
    assert payload["kinds"]["member"]["removed"][0]["name"] == "Solo"

    payload2 = context_store.diff_records(session, "nope-a", "nope-b")
    assert payload2["kinds"] == {}


async def test_store_diff_zero_record_version(session):
    proj = projects.get_default_project(session)
    empty_cv = _persist(session, proj.id, [], "empty")
    full_cv = _persist(session, proj.id, [_rec(name=f"M{i}") for i in range(5)], "full")
    session.commit()
    payload = context_store.diff_records(session, empty_cv.id, full_cv.id)
    assert len(payload["kinds"]["member"]["added"]) == 5


async def test_store_diff_cross_project_is_safe(session):
    # The store does NOT enforce project match (the route does). Verify the store
    # at least never crashes and produces a well-formed diff across projects.
    proj = projects.get_default_project(session)
    other = projects.create_project(session, name="Other") if hasattr(projects, "create_project") else None
    a = _persist(session, proj.id, [_rec(name="A")], "a")
    other_pid = other.id if other is not None else proj.id
    b = _persist(session, other_pid, [_rec(name="B")], "b")
    session.commit()
    payload = context_store.diff_records(session, a.id, b.id)
    _shape_ok(payload["kinds"]["member"])


# --------------------------------------------------------------------------- #
# build_tenant_metadata robustness
# --------------------------------------------------------------------------- #
async def test_build_metadata_skips_invalid_member_gracefully(session):
    proj = projects.get_default_project(session)
    records = [
        # valid member
        _rec(kind="member", name="Good", dimension="Account",
             data={"name": "Good", "dimension": "Account", "application": "APP"}),
        # invalid: data missing required 'dimension'/'application'
        _rec(kind="member", name="BadMissing", dimension="Account",
             data={"name": "BadMissing"}),
        # invalid: wrong type for 'children'
        _rec(kind="member", name="BadType", dimension="Account",
             data={"name": "BadType", "dimension": "Account", "application": "APP",
                   "children": "not-a-list"}),
        # data with unknown provenance keys (must be filtered, still valid)
        _rec(kind="member", name="Prov", dimension="Account",
             data={"name": "Prov", "dimension": "Account", "application": "APP",
                   "source": "snapshot", "referencedOnly": True, "junk": {"x": 1}}),
    ]
    cv = _persist(session, proj.id, records, "meta")
    session.commit()
    md = context_store.build_tenant_metadata(session, cv.id)  # must not raise
    names = {m.name for byname in md.members.values() for m in byname.values()}
    assert "Good" in names and "Prov" in names
    assert "BadMissing" not in names and "BadType" not in names


async def test_build_metadata_non_dict_and_none_data(session):
    proj = projects.get_default_project(session)
    records = [
        {"kind": "cube", "name": "C", "dimension": None, "cube": "C",
         "alias": None, "parent": None, "application": "APP",
         "search_text": "c", "data": None},                       # None data
        {"kind": "dimension", "name": "D", "dimension": "D", "cube": None,
         "alias": None, "parent": None, "application": "APP",
         "search_text": "d", "data": ["not", "a", "dict"]},        # list data
        # a valid cube so the build has something to keep
        _rec(kind="cube", name="Real", dimension=None, cube="Real",
             data={"name": "Real", "application": "APP"}),
    ]
    cv = _persist(session, proj.id, records, "meta2")
    session.commit()
    md = context_store.build_tenant_metadata(session, cv.id)  # must not raise
    assert "Real" in md.cubes
    assert "C" not in md.cubes  # None data -> missing required 'application' -> skipped


async def test_build_metadata_unknown_kinds_ignored(session):
    proj = projects.get_default_project(session)
    records = [_rec(kind="application", name="App", data={"name": "App"}),
               _rec(kind="mystery", name="Z", data={"foo": "bar"})]
    cv = _persist(session, proj.id, records, "meta3")
    session.commit()
    md = context_store.build_tenant_metadata(session, cv.id)  # must not raise
    assert md.cubes == {} and md.members == {}
