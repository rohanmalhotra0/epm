"""Adversarial fuzz/hardening tests for the LCM snapshot parser + merge.

Throws hostile and edge-case inputs at ``analyze_snapshot`` and
``merge_snapshot_into_context`` and asserts the CONTRACT:

* ``analyze_snapshot`` either returns a valid ``SnapshotBundle`` OR raises
  ``SnapshotError`` — never any other uncaught exception, hang, OOM, network
  access, or disk write.
* A single malformed/hostile artifact never aborts the whole parse: it adds an
  ``issues`` entry and every other component still parses (the module's stated
  degradation contract).
* ``merge_snapshot_into_context`` never crashes or corrupts, and never mutates a
  prior ContextVersion.

Regression coverage for defects found by fuzzing (see the module header of
``app/context/snapshot.py``):

* an oversized field in a dimension-CSV **header row** used to raise ``csv.Error``
  out of ``_dimension_header`` and abort the whole snapshot;
* a deeply nested (hostile) rule XML used to blow the Python stack with a
  ``RecursionError`` in the recursive ``_iter_outside_templates`` walk;
* an oversized field in the HSS ``Groups.csv`` used to raise ``csv.Error`` out of
  ``_parse_hss`` and abort the whole snapshot.

All three now degrade to an ``issues`` entry with the rest of the snapshot intact.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.context import (
    SnapshotError,
    analyze_snapshot,
    build_context,
    merge_snapshot_into_context,
)
from app.context import snapshot as snapshot_mod
from app.connector import DemoConnector
from app.services import context_store
from app.services import projects as projects_svc

_APP = "ACME_PLN"
_HP = f"HP-{_APP}"
_DIMS = f"{_HP}/resource/Global Artifacts/Common Dimensions/Standard Dimensions"
_GLOBAL = f"{_HP}/resource/Global Artifacts"
_CALC = "CALC-Calculation Manager/resource/Planning"


# --- minimal synthetic builder -------------------------------------------------


def _dim_csv(dimension: str, rows: list[str], *, header: str | None = None,
             dim_type: str = "None") -> str:
    header_block = (
        "﻿#!-- HEADERBLOCK DIMENSION XML\n"
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        "<DIMENSIONS>\n"
        f' <Dimension name="{dimension}" density="Sparse" dimensionType="{dim_type}">\n'
        " </Dimension>\n"
        "</DIMENSIONS>\n"
        "#--!\n"
    )
    if header is None:
        header = (f"{dimension}, Parent, Alias: Default, Data Storage, Formula, Data Type, UDA,"
                  " Smart List, Description, Aggregation (Plan1), Data Storage (Plan1)")
    return header_block + header + "\n" + "\n".join(rows) + "\n"


def _acct_csv() -> str:
    return _dim_csv("Account", ["Account,,,,,,,,,,",
                                "Salaries,Account,Base Salaries,store data,,currency,,,,+,store data"],
                    dim_type="Account")


def _zip_bytes(files: dict[str, object], prefix: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, text in sorted(files.items(), key=lambda kv: kv[0]):
            data = text if isinstance(text, bytes) else str(text).encode("utf-8")
            zf.writestr(prefix + path, data)
    return buf.getvalue()


def _base(extra: dict[str, object] | None = None) -> bytes:
    """A minimally valid snapshot (one HP dimension) plus any extra members."""
    files: dict[str, object] = {f"{_DIMS}/Account.csv": _acct_csv()}
    if extra:
        files.update(extra)
    return _zip_bytes(files)


# --- the hard contract: bundle-or-SnapshotError, never anything else ----------


def _assert_contract(data: bytes):
    """analyze_snapshot must return a SnapshotBundle or raise SnapshotError."""
    try:
        bundle = analyze_snapshot(data, filename="fuzz.zip")
    except SnapshotError:
        return None
    assert bundle.analysis is not None
    # bundle records must be well-formed dicts
    for rec in bundle.records:
        assert isinstance(rec, dict) and "kind" in rec and "name" in rec
    return bundle


# --- malformed / adversarial zips ---------------------------------------------


def test_not_a_zip():
    with pytest.raises(SnapshotError):
        analyze_snapshot(b"this is definitely not a zip archive at all")


def test_empty_bytes():
    with pytest.raises(SnapshotError):
        analyze_snapshot(b"")


def test_empty_zip():
    with pytest.raises(SnapshotError):
        analyze_snapshot(_zip_bytes({}))


def test_zip_with_only_a_directory_entry():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("some_dir/", "")
        zf.writestr("HP-X/nested_dir/", "")
    with pytest.raises(SnapshotError):
        analyze_snapshot(buf.getvalue())


def test_truncated_zip():
    good = _base()
    with pytest.raises(SnapshotError):
        analyze_snapshot(good[: len(good) // 2])
    with pytest.raises(SnapshotError):
        analyze_snapshot(good[:22])  # cut inside the local header


def test_structureless_zip_is_rejected():
    with pytest.raises(SnapshotError):
        analyze_snapshot(_zip_bytes({"random/notes.txt": "hello", "a/b/c.dat": "x"}))


def test_nested_zip_entry_is_ignored_not_recursed():
    inner = _base()
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Account.csv": _acct_csv(), "payload/inner.zip": inner}))
    assert bundle is not None
    assert bundle.analysis.application == _APP
    # the nested zip's members were never surfaced
    assert not any(r.get("name") == "Salaries" and r.get("dimension") is None for r in bundle.records)


def test_encrypted_entry_is_skipped_not_fatal():
    # zipfile can list an AES/ZipCrypto entry but read() raises RuntimeError;
    # read_text swallows it into an issue.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{_DIMS}/Account.csv", _acct_csv())
        zi = zipfile.ZipInfo(f"{_HP}/resource/Global Artifacts/Substitution Variables/Enc.xml")
        zf.writestr(zi, "<substitutionVariable><name>x</name></substitutionVariable>")
        # flag the entry as encrypted so read() raises
        for info in zf.infolist():
            if info.filename.endswith("Enc.xml"):
                info.flag_bits |= 0x1
    bundle = _assert_contract(buf.getvalue())
    assert bundle is not None and bundle.analysis.application == _APP


# --- zip-bomb / resource caps -------------------------------------------------


def test_total_uncompressed_cap_triggers():
    bomb = _zip_bytes({f"{_DIMS}/Account.csv": _acct_csv(),
                       "junk/big.txt": "0" * (500 * 1024 * 1024)})
    assert len(bomb) < 2 * 1024 * 1024  # highly compressible, small on disk
    with pytest.raises(SnapshotError, match="uncompressed size cap"):
        analyze_snapshot(bomb)


def test_entries_cap_triggers():
    files: dict[str, object] = {f"junk/f{i}.txt": "x" for i in range(snapshot_mod._MAX_ENTRIES + 5)}
    files[f"{_DIMS}/Account.csv"] = _acct_csv()
    with pytest.raises(SnapshotError, match="too many entries"):
        analyze_snapshot(_zip_bytes(files))


def test_per_entry_text_cap_skips_single_oversized_entry():
    over = _dim_csv("Huge", ["Huge,,"]) + "x" * (snapshot_mod._MAX_TEXT_ENTRY + 1024)
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Account.csv": _acct_csv(), f"{_DIMS}/Huge.csv": over}))
    assert bundle is not None
    assert any("oversized entry" in i for i in bundle.analysis.issues)
    assert "Account" in bundle.analysis.dimensions  # the rest still parsed


def test_record_cap_triggers_on_amplified_member_csv():
    rows = ["Account,,"] + [f"M{i},Account,a" for i in range(snapshot_mod._MAX_RECORDS + 5000)]
    with pytest.raises(SnapshotError, match="record cap"):
        analyze_snapshot(_zip_bytes({f"{_DIMS}/Account.csv": _dim_csv("Account", rows)}))


def test_oversized_field_in_data_row_is_issue_not_crash():
    big = _dim_csv("Account", ["Account,,,,,,,,,,",
                               '"' + "x" * 200_000 + '",Account,,,,,,,,,'])
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Account.csv": _acct_csv(),
                                          f"{_DIMS}/Big.csv": big}))
    assert bundle is not None
    assert any("Big.csv" in i for i in bundle.analysis.issues)
    assert "Account" in bundle.analysis.dimensions


def test_oversized_field_in_HEADER_row_is_issue_not_fatal():
    # REGRESSION: header row field > csv default field limit used to raise
    # csv.Error out of _dimension_header and abort the entire snapshot.
    poison_header = "A" * 200_000 + ", Parent, Alias: Default"
    poison = _dim_csv("Big", ["Big,,"], header=poison_header)
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Account.csv": _acct_csv(),
                                          f"{_DIMS}/Big.csv": poison}))
    assert bundle is not None
    assert bundle.analysis.application == _APP
    assert "Account" in bundle.analysis.dimensions  # untouched dimension survives
    assert bundle.analysis.counts.get("members") == 2  # Account.csv members intact
    # the poison dimension contributed no members but its record still exists
    assert not any(r["kind"] == "member" and r["dimension"] == "Big" for r in bundle.records)
    assert any("Big.csv" in i for i in bundle.analysis.issues)


def test_oversized_field_in_hss_groups_is_issue_not_fatal():
    # REGRESSION: an oversized field in Groups.csv used to raise csv.Error out of
    # _parse_hss and abort the entire snapshot.
    groups = "#group\nid,provider,name\n1,ND," + "z" * 200_000 + "\n2,ND,Planners\n"
    bundle = _assert_contract(_zip_bytes({
        f"{_DIMS}/Account.csv": _acct_csv(),
        "HSS-Shared Services/resource/Native Directory/Groups.csv": groups}))
    assert bundle is not None
    assert bundle.analysis.application == _APP
    assert any("groups" in i.lower() for i in bundle.analysis.issues)


# --- XML attacks --------------------------------------------------------------


def test_xxe_external_file_read_is_blocked(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP_SECRET_SENTINEL_VALUE")
    xxe = f"""<?xml version="1.0"?>
<!DOCTYPE p [ <!ENTITY xxe SYSTEM "file://{secret}"> ]>
<Package><Task><Source product="HP" application="&xxe;"/><Target filePath="/HP-{_APP}"/></Task></Package>"""
    bundle = _assert_contract(_zip_bytes({"Export.xml": xxe, f"{_DIMS}/Account.csv": _acct_csv()}))
    assert bundle is not None
    # the entity must never have been resolved -> the sentinel appears nowhere
    blob = repr(bundle.analysis.model_dump()) + repr(bundle.records)
    assert "TOP_SECRET_SENTINEL_VALUE" not in blob
    # defusedxml rejected the DTD/entity -> Export.xml logged an issue, and app
    # detection fell back to the folder name
    assert bundle.analysis.application == _APP
    assert any("Export.xml" in i for i in bundle.analysis.issues)


def test_xxe_in_substitution_variable_is_blocked(tmp_path):
    secret = tmp_path / "s.txt"
    secret.write_text("SENTINEL_XXE_SUBVAR")
    xxe = f"""<?xml version="1.0"?>
<!DOCTYPE v [ <!ENTITY x SYSTEM "file://{secret}"> ]>
<substitutionVariable><name>&x;</name><value>&x;</value></substitutionVariable>"""
    bundle = _assert_contract(_base({
        f"{_GLOBAL}/Substitution Variables/Evil.xml": xxe}))
    assert bundle is not None
    assert "SENTINEL_XXE_SUBVAR" not in repr(bundle.records)


def test_billion_laughs_is_blocked():
    lol = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
 <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
]>
<substitutionVariable><name>&lol5;</name><value>x</value></substitutionVariable>"""
    bundle = _assert_contract(_base({f"{_GLOBAL}/Substitution Variables/Lol.xml": lol}))
    assert bundle is not None
    # expansion never happened -> no gigabyte "lol" string anywhere
    assert not any(len(str(r)) > 1_000_000 for r in bundle.records)
    assert any("Lol.xml" in i for i in bundle.analysis.issues)


def test_deeply_nested_rule_xml_does_not_blow_the_stack():
    # REGRESSION: recursive _iter_outside_templates blew the Python stack
    # (RecursionError) and aborted the whole snapshot; now iterative.
    depth = 60_000
    deep = "<w>" * depth + "</w>" * depth
    rule = f"<HBRRepo><rules><rule name='R'><script type='groovy'>{deep}</script></rule></rules></HBRRepo>"
    bundle = _assert_contract(_zip_bytes({
        f"{_CALC}/{_APP}/Plan1/Rules/R": rule, f"{_DIMS}/Account.csv": _acct_csv()}))
    assert bundle is not None
    assert bundle.analysis.application == _APP


def test_deeply_nested_export_tree_does_not_crash():
    deep = "<x>" * 100_000 + "</x>" * 100_000
    _assert_contract(_zip_bytes({"Export.xml": f"<Package>{deep}</Package>",
                                 f"{_DIMS}/Account.csv": _acct_csv()}))


def test_unbalanced_cdata_in_rule_is_issue_not_fatal():
    bundle = _assert_contract(_zip_bytes({
        f"{_CALC}/{_APP}/Plan1/Rules/R":
            "<HBRRepo><rules><rule name='R'><script><![CDATA[AGG(]]</script></rule></rules></HBRRepo>",
        f"{_DIMS}/Account.csv": _acct_csv()}))
    assert bundle is not None
    assert any("Rules/R" in i for i in bundle.analysis.issues)
    assert "Account" in bundle.analysis.dimensions


def test_malformed_navflow_usagexml_cdata_is_issue_not_fatal():
    bundle = _assert_contract(_base({
        f"{_GLOBAL}/Navigation Flows/N.xml":
            "<fuseStructure><usageXML><![CDATA[<not valid xml <<]]></usageXML></fuseStructure>"}))
    assert bundle is not None
    assert any("usageXML" in i for i in bundle.analysis.issues)


def test_wrong_declared_encoding_does_not_crash():
    # bytes are utf-8 but the prolog claims UTF-16
    xml = ('<?xml version="1.0" encoding="UTF-16"?>'
           f'<Package><Task><Source product="HP" application="{_APP}"/>'
           f'<Target filePath="/HP-{_APP}"/></Task></Package>')
    _assert_contract(_zip_bytes({"Export.xml": xml, f"{_DIMS}/Account.csv": _acct_csv()}))


# --- path / traversal ---------------------------------------------------------


def test_traversal_and_absolute_paths_are_skipped():
    bundle = _assert_contract(_zip_bytes({
        f"{_DIMS}/Account.csv": _acct_csv(),
        "../evil.csv": "Account,Parent\nHacked,",
        "/abs/evil2.csv": "Account,Parent\nHacked2,",
        "a/../../evil3.csv": "Account,Parent\nHacked3,",
    }))
    assert bundle is not None
    unsafe = [i for i in bundle.analysis.issues if "unsafe path" in i]
    assert len(unsafe) >= 2
    assert not any(str(r.get("name", "")).startswith("Hacked") for r in bundle.records)


def test_backslash_paths_are_normalized():
    win = _HP.replace("/", "\\") + "\\resource\\Global Artifacts\\Common Dimensions\\Standard Dimensions\\Account.csv"
    bundle = _assert_contract(_zip_bytes({win: _acct_csv()}))
    assert bundle is not None
    assert bundle.analysis.application == _APP
    assert "Account" in bundle.analysis.dimensions


def test_colon_drive_prefix_is_skipped():
    bundle = _assert_contract(_zip_bytes({
        f"{_DIMS}/Account.csv": _acct_csv(),
        f"C:/{_DIMS}/Account.csv": _dim_csv("Account", ["Account,,", "Hacked,Account,x"])}))
    assert bundle is not None
    assert any("unsafe path" in i for i in bundle.analysis.issues)
    assert not any(r.get("name") == "Hacked" for r in bundle.records)


def test_null_byte_and_long_and_unicode_names_do_not_crash():
    bundle = _assert_contract(_zip_bytes({
        f"{_DIMS}/Account.csv": _acct_csv(),
        f"{_DIMS}/na\x00me.csv": _dim_csv("Weird", ["Weird,,", "W,Weird,a"]),
        f"{_DIMS}/" + "L" * 3000 + ".csv": _dim_csv("Long", ["Long,,", "LM,Long,a"]),
        f"{_DIMS}/emoji\U0001F680.csv": _dim_csv("Emoji", ["Emoji,,", "🚀‮RTL,Emoji,a"]),
    }))
    assert bundle is not None
    assert bundle.analysis.application == _APP


def test_essbase_data_entries_are_excluded():
    bundle = _assert_contract(_zip_bytes({
        f"{_DIMS}/Account.csv": _acct_csv(),
        f"{_HP}/resource/Essbase Data/Plan1/data.txt": "secret essbase payload",
    }))
    assert bundle is not None
    assert not any("essbase payload" in str(r).lower() for r in bundle.records)


# --- content edge cases -------------------------------------------------------


def test_dimension_missing_sentinel_still_parses_members():
    # HEADERBLOCK present but no closing #--! sentinel line
    text = ("﻿#!-- HEADERBLOCK DIMENSION XML\n<?xml version='1.0'?>\n<DIMENSIONS>\n"
            "<Dimension name='Acct' density='Sparse'/>\n</DIMENSIONS>\n"
            "Acct, Parent, Alias: Default\nA,,al\n")
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Acct.csv": text}))
    assert bundle is not None


def test_dimension_without_headerblock_parses_as_plain_csv():
    text = "Acct, Parent, Alias: Default\nA,,al\nB,A,b2\n"
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Acct.csv": text}))
    assert bundle is not None
    assert "Acct" in bundle.analysis.dimensions


def test_header_row_only_no_members():
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Empty.csv": _dim_csv("Empty", [])}))
    assert bundle is not None
    assert bundle.analysis.counts.get("members", 0) == 0


def test_duplicate_member_names_do_not_crash():
    dup = _dim_csv("Account", ["Account,,,,,,,,,,",
                               "A,Account,al1", "A,Account,al2", "A,Account,al3"])
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Account.csv": dup}))
    assert bundle is not None


def test_member_with_newlines_commas_quotes_in_name_and_alias():
    weird = _dim_csv("Account", ["Account,,,,,,,,,,",
                                 '"Line1\nLine2",Account,"comma,alias"',
                                 '"He said ""hi""",Account,x'])
    bundle = _assert_contract(_zip_bytes({f"{_DIMS}/Account.csv": weird}))
    assert bundle is not None
    names = {r["name"] for r in bundle.records if r["kind"] == "member"}
    assert "Line1\nLine2" in names


def test_rule_file_with_no_script_element():
    bundle = _assert_contract(_zip_bytes({
        f"{_CALC}/{_APP}/Plan1/Rules/NoScript":
            "<HBRRepo><rules><rule name='NoScript'><property name='plantype'>Plan1</property></rule></rules></HBRRepo>",
        f"{_DIMS}/Account.csv": _acct_csv()}))
    assert bundle is not None
    rule = next((r for r in bundle.records if r["kind"] == "rule"), None)
    assert rule is not None and rule["data"]["body"] == ""


def test_unexpected_roots_for_deep_parsers_degrade_to_name_only():
    bundle = _assert_contract(_base({
        f"{_GLOBAL}/Smart Lists/S.xml": "<totallyDifferentRoot><junk/></totallyDifferentRoot>",
        f"{_GLOBAL}/Data Maps/D.xml": "<nope/>",
        f"{_GLOBAL}/Valid Intersections/V.xml": "<xyzzy/>",
        f"{_GLOBAL}/Dashboards/Dash.xml": "<random/>",
    }))
    assert bundle is not None
    # each present-but-unmatched file yields a name-only record, no crash
    kinds = {r["kind"] for r in bundle.records}
    assert {"smartList", "dataMap", "validIntersection", "dashboard"} <= kinds


def test_form_with_wrong_root_is_issue_plus_name_only():
    bundle = _assert_contract(_base({f"{_GLOBAL}/Data Forms/NotAForm.xml": "<somethingElse/>"}))
    assert bundle is not None
    assert any("NotAForm.xml" in i for i in bundle.analysis.issues)
    forms = [r for r in bundle.records if r["kind"] == "form" and r["name"] == "NotAForm"]
    assert len(forms) == 1 and "definition" not in forms[0]["data"]


# --- app detection ------------------------------------------------------------


def test_export_with_no_hp_task_still_detects_from_folder():
    exp = ('<Package><Task><Source product="AIF" application="FDM"/>'
           '<Target filePath="/FDMEE-FDM"/></Task></Package>')
    bundle = _assert_contract(_zip_bytes({"Export.xml": exp, f"{_DIMS}/Account.csv": _acct_csv()}))
    assert bundle is not None
    # no HP task named it, but the HP-ACME_PLN folder does
    assert bundle.analysis.application == _APP


def test_multiple_hp_apps_do_not_crash():
    exp = """<Package>
<Task><Source product="HP" application="APP1"/><Target filePath="/HP-APP1"/></Task>
<Task><Source product="HP" application="APP2"/><Target filePath="/HP-APP2"/></Task>
</Package>"""
    d1 = "HP-APP1/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Account.csv"
    d2 = "HP-APP2/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Entity.csv"
    bundle = _assert_contract(_zip_bytes({
        "Export.xml": exp, d1: _acct_csv(),
        d2: _dim_csv("Entity", ["Entity,,", "E,Entity,e"], dim_type="Entity")}))
    assert bundle is not None
    assert bundle.analysis.application in ("APP1", "APP2")
    assert {"APP1", "APP2"} <= set(bundle.analysis.applications)


def test_very_long_and_special_app_name():
    longapp = "A" * 5000
    exp = (f'<Package><Task><Source product="HP" application="{longapp}"/>'
           f'<Target filePath="/HP-{longapp}"/></Task></Package>')
    d = f"HP-{longapp}/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Account.csv"
    bundle = _assert_contract(_zip_bytes({"Export.xml": exp, d: _acct_csv()}))
    assert bundle is not None
    assert bundle.analysis.application == longapp


def test_missing_import_xml_yields_no_provenance():
    bundle = _assert_contract(_base())
    assert bundle is not None
    assert bundle.analysis.provenance is None


# --- battery: every hostile input satisfies the hard contract -----------------


def test_contract_battery_never_raises_unexpected():
    hostile = [
        b"",
        b"PK\x03\x04 corrupt",
        b"not a zip",
        _zip_bytes({}),
        _zip_bytes({"x/y.txt": "z"}),
        _base()[:40],
        _base({"../e.csv": "Account\nX"}),
        _base({f"{_GLOBAL}/Data Forms/B.xml": "<form"}),
        _base({f"{_CALC}/{_APP}/Plan1/Rules/R": "<HBRRepo><rules><rule name='R'"}),
        _base({f"{_GLOBAL}/Substitution Variables/S.xml": "<broken"}),
    ]
    for i, data in enumerate(hostile):
        # must not raise anything other than SnapshotError
        try:
            _assert_contract(data)
        except SnapshotError:
            pass  # allowed
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"hostile input #{i} raised {type(exc).__name__}: {exc}")


# --- merge attacks ------------------------------------------------------------


async def test_merge_normalization_collision_adopts_live_app(session):
    proj = projects_svc.create_project(session, "FuzzNormCollide")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                  live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    # snapshot app "M.C.W_P.C.F" normalizes to the same as live "MCWPCF"
    exp = ('<Package><Task><Source product="HP" application="M.C.W_P.C.F"/>'
           '<Target filePath="/HP-M.C.W_P.C.F"/></Task></Package>')
    d = "HP-M.C.W_P.C.F/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Account.csv"
    bundle = analyze_snapshot(_zip_bytes({"Export.xml": exp, d: _acct_csv()}))
    cv = merge_snapshot_into_context(session, proj.id, bundle)
    session.flush()
    assert cv.mode == "hybrid"
    assert cv.application == "MCWPCF"
    apps = context_store.get_records(session, cv.id, kind="application")
    assert [a.name for a in apps] == ["MCWPCF"]  # no duplicate application record


async def test_merge_zero_record_snapshot_is_safe(session):
    proj = projects_svc.create_project(session, "FuzzZeroRec")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    cv1 = context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                        live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    before = len(context_store.get_records(session, cv1.id))

    # a valid component with no parseable records
    bundle = analyze_snapshot(_zip_bytes({
        "Export.xml": '<Package><Task><Source product="HP" application="EMPTY"/>'
                      '<Target filePath="/HP-EMPTY"/></Task></Package>',
        "HP-EMPTY/resource/keep.txt": "x"}))
    cv2 = merge_snapshot_into_context(session, proj.id, bundle)
    session.flush()
    session.expire_all()
    # prior version untouched; live records carried forward
    assert len(context_store.get_records(session, cv1.id)) == before
    assert cv2.id != cv1.id and cv2.active is True


async def test_merge_member_name_collision_across_parent_replaces_by_key(session):
    proj = projects_svc.create_project(session, "FuzzNameCollide")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                  live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    # A snapshot member "Salaries" in Account with a DIFFERENT parent than live —
    # same record key (kind, dim, name) so it replaces, never duplicates.
    snap = _dim_csv("Account", ["Account,,,,,,,,,,",
                                "Salaries,DifferentParent,Snap Alias,store data,,currency,,,,+,store data"],
                    dim_type="Account")
    exp = ('<Package><Task><Source product="HP" application="MCW_PCF"/>'
           '<Target filePath="/HP-MCW_PCF"/></Task></Package>')
    d = "HP-MCW_PCF/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Account.csv"
    bundle = analyze_snapshot(_zip_bytes({"Export.xml": exp, d: snap}))
    cv = merge_snapshot_into_context(session, proj.id, bundle)
    session.flush()
    salaries = [r for r in context_store.get_records(session, cv.id, kind="member")
                if r.name == "Salaries" and r.dimension == "Account"]
    assert len(salaries) == 1  # replaced, not duplicated
    assert salaries[0].data["source"] == "snapshot"


async def test_merge_never_mutates_prior_version(session):
    proj = projects_svc.create_project(session, "FuzzImmutable")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    cv1 = context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                        live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    before = len(context_store.get_records(session, cv1.id))
    old_alias = next(r.alias for r in context_store.get_records(session, cv1.id, kind="member")
                     if r.name == "Salaries")

    exp = ('<Package><Task><Source product="HP" application="MCW_PCF"/>'
           '<Target filePath="/HP-MCW_PCF"/></Task></Package>')
    d = "HP-MCW_PCF/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Account.csv"
    bundle = analyze_snapshot(_zip_bytes({"Export.xml": exp, d: _acct_csv()}))
    cv2 = merge_snapshot_into_context(session, proj.id, bundle)
    session.flush()
    session.expire_all()

    assert cv2.id != cv1.id
    assert len(context_store.get_records(session, cv1.id)) == before
    assert next(r.alias for r in context_store.get_records(session, cv1.id, kind="member")
                if r.name == "Salaries") == old_alias
