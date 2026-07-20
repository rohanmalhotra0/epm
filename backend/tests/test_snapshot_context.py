"""LCM application-snapshot analyzer + context merge tests.

The synthetic zip builder uses a dynamic application name (ACME_PLN by default)
to prove nothing is hardcoded; one test additionally zips a real subset of the
repo's "Artifact Snapshot" fixture when present.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.connector import DemoConnector
from app.context import (
    SnapshotError,
    analyze_snapshot,
    build_context,
    merge_snapshot_into_context,
    summarize_snapshot,
)
from app.context import snapshot as snapshot_mod
from app.services import context_store
from app.services import projects as projects_svc

_FIXTURE = Path(__file__).resolve().parents[2] / "Artifact Snapshot"


# --- synthetic snapshot builder ------------------------------------------------


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
    return "\ufeff" + header_block + header + "\n" + "\n".join(rows) + "\n"


def _sub_var(name: str, value: str, plan_type: str = "ALL") -> str:
    return ('<?xml version="1.0" encoding="UTF-8" ?>\n <substitutionVariable>\n'
            f" <name>{name}</name>\n <value>{value}</value>\n <planType>{plan_type}</planType>\n"
            "</substitutionVariable>\n")


_USER_VARS = """<?xml version="1.0" encoding="UTF-8" ?>
 <UserVariables xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" >
 <UserVariable Name="UV_Entity" ContextSensitive="false" Dimension="Entity" >
 <mbrSelection>IDescendants(Entity)</mbrSelection>
</UserVariable>
 <UserVariable Name="UV_Account" ContextSensitive="false" Dimension="Account" >
 <mbrSelection>IDescendants(Account)</mbrSelection>
</UserVariable>
</UserVariables>
"""

_NAV_FLOW = """<?xml version="1.0" encoding="UTF-8" ?>
 <fuseStructure name="Admin" xmlns="http://xmlns.oracle.com/epm/common/structure" >
 <usageXML><![CDATA[<?xml version = '1.0' encoding = 'UTF-8'?>
<fuseStructureUsage xmlns="http://xmlns.oracle.com/epm/common/structure">
   <categories><category id="X"><card id="C1"><tab id="T1">
      <tfParameters>
         <tfParameter artifactUID="" name="displayHeader" value="Y" artifactName=""/>
         <tfParameter artifactUID="7~~~Rolling Forecast" name="formId" artifactName="Rolling Forecast"/>
         <tfParameter artifactUID="107~~~Summary Dashboard" name="formId" artifactName="Summary Dashboard"/>
      </tfParameters>
   </tab></card></category></categories>
</fuseStructureUsage>]]></usageXML>
</fuseStructure>
"""

_RULE_XML = """<?xml version = '1.0' encoding = 'UTF-8'?>
<HBRRepo><variables><variable name="RTP_Entity" type="member" usage="const" id="1" product="Planning"><property name="prompt_text">Select entity</property><value/></variable></variables><rulesets/><rules><rule id="1" name="Calc All" product="Planning"><property name="application">__APP__</property><property name="plantype">Plan1</property><variable_references><variable_reference name="RTP_Entity" id="1"/><variable_reference name="RTP_Version" id="2"/></variable_references><script type="groovy">def x = 1
if (x &lt; 2) { println "run" }
%Template(name:="Util_GT",plantype:="Plan1")</script></rule></rules><templates/></HBRRepo>"""

_TEMPLATE_XML = """<?xml version = '1.0' encoding = 'UTF-8'?>
<HBRRepo><templates><template name="Util_GT" product="Planning"><script type="calcscript"><![CDATA[AGG("Plan1");]]></script></template></templates></HBRRepo>"""

_IMPORT_FORMAT = """<?xml version = '1.0' encoding = 'UTF-8'?>
<ImportFormats><ImportGroupsFileLcmVO><ImportGroupsFileLcmVORow>
<Impgroupkey>DATA_DAILY</Impgroupkey><Impgroupfiletype>DELIMITED</Impgroupfiletype>
</ImportGroupsFileLcmVORow></ImportGroupsFileLcmVO></ImportFormats>"""

_LOCATION = """<?xml version = '1.0' encoding = 'UTF-8'?>
<LocationForLcmVO><LocationForLcmVORow><Partname>LOC_DAILY</Partname></LocationForLcmVORow></LocationForLcmVO>"""

_PIPELINE = """<?xml version = '1.0' encoding = 'UTF-8'?>
<PIPELINEDEFINITION><PIPELINENAME>DAILY_PIPE</PIPELINENAME><JSONVALUE>{"variables":[],"stages":[{"id":1},{"id":2}]}</JSONVALUE></PIPELINEDEFINITION>"""

_GROUPS_CSV = "#group\nid,provider,name,description,internal_id\n1,Native Directory,Admins,,a\n2,Native Directory,Planners,,b\n"
_USERS_CSV = "#user\nFirst Name,Last Name,Email,User Login\nA,B,a@x.com,a\nC,D,c@x.com,c\nE,F,e@x.com,e\n"


def _export_xml(app: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Package>
   <LOCALE>en_US</LOCALE>
   <Task>
      <Source type="Application" product="HUB" project="Foundation" application="Shared Services"/>
      <Target type="FileSystem" filePath="/HSS-Shared Services"/>
   </Task>
   <Task>
      <Source type="Application" product="HP" project="Default Application Group" application="{app}"/>
      <Target type="FileSystem" filePath="/HP-{app}"/>
   </Task>
   <Task>
      <Source type="Application" product="CALC" project="Foundation" application="Calculation Manager"/>
      <Target type="FileSystem" filePath="/CALC-Calculation Manager"/>
   </Task>
   <Task>
      <Source type="Application" product="AIF" project="FDM" application="FDM Enterprise Edition"/>
      <Target type="FileSystem" filePath="/FDMEE-FDM Enterprise Edition"/>
   </Task>
</Package>"""


_IMPORT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Package>
   <LOCALE>en_US</LOCALE>
   <ExportedVersion>26.07.95</ExportedVersion>
   <ExportedDateUTC>20260718</ExportedDateUTC>
   <ExportedTimeUTC>09:30</ExportedTimeUTC>
   <ExportedBy>cloud_admin</ExportedBy>
   <IDMDomain>acme2026</IDMDomain>
   <ServiceInstance>acme-test</ServiceInstance>
</Package>"""


def _snapshot_files(app_name: str) -> dict[str, str]:
    hp = f"HP-{app_name}"
    dims = f"{hp}/resource/Global Artifacts/Common Dimensions/Standard Dimensions"
    calc = f"CALC-Calculation Manager/resource/Planning/{app_name}/Plan1"
    fdmee = "FDMEE-FDM Enterprise Edition/resource"
    return {
        "Export.xml": _export_xml(app_name),
        "Import.xml": _IMPORT_XML,
        f"{dims}/Account.csv": _dim_csv("Account", [
            "Account,,,,,,,,,,",
            "Salaries,Account,Snapshot Salaries,store data,,currency,,,,+,store data",
        ], dim_type="Account"),
        f"{dims}/Entity.csv": _dim_csv("Entity", [
            "Entity,,,,,,,,,,",
            "E100,Entity,East Region,store data,,,,,,+,store data",
        ], dim_type="Entity"),
        f"{hp}/resource/Cube/Plan1/Cube Properties.xml": "<cube/>",
        f"{hp}/resource/Cube/Cash/Cube Properties.xml": "<cube/>",
        f"{hp}/resource/Global Artifacts/Substitution Variables/CurYr.xml": _sub_var("CurYr", "FY26"),
        f"{hp}/resource/Cube/Plan1/Substitution Variables/CashStart.xml": _sub_var("CashStart", "Jan", "Plan1"),
        f"{hp}/resource/Configuration/User Variables.xml": _USER_VARS,
        f"{hp}/resource/Global Artifacts/Navigation Flows/Admin.xml": _NAV_FLOW,
        f"{calc}/Rules/Calc All": _RULE_XML.replace("__APP__", app_name),
        f"{calc}/Templates/Util_GT": _TEMPLATE_XML,
        f"{fdmee}/Application Data/Planning Applications/{app_name}-Plan1/Import Format.xml": _IMPORT_FORMAT,
        f"{fdmee}/Application Data/Planning Applications/{app_name}-Plan1/Location.xml": _LOCATION,
        f"{fdmee}/Cross Application Data/Pipeline Definition/DAILY_PIPE.xml": _PIPELINE,
        "HSS-Shared Services/resource/Native Directory/Groups.csv": _GROUPS_CSV,
        "HSS-Shared Services/resource/External Directory/Users.csv": _USERS_CSV,
    }


def _zip_bytes(files: dict[str, str], prefix: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, text in sorted(files.items()):
            zf.writestr(prefix + path, text.encode("utf-8"))
    return buf.getvalue()


def _make_snapshot_zip(app_name: str = "ACME_PLN", prefix: str = "", **overrides: str | None) -> bytes:
    files = _snapshot_files(app_name)
    for path, text in overrides.items():
        if text is None:
            files.pop(path, None)
        else:
            files[path] = text
    return _zip_bytes(files, prefix)


# --- analyzer -------------------------------------------------------------------


def test_analyze_dynamic_app_detection_and_counts():
    bundle = analyze_snapshot(_make_snapshot_zip(), filename="acme.zip")
    a = bundle.analysis
    assert a.filename == "acme.zip"
    assert a.application == "ACME_PLN"
    assert a.applications == ["ACME_PLN", "Calculation Manager", "FDM Enterprise Edition", "Shared Services"]
    assert a.cubes == ["Cash", "Plan1"]
    assert a.dimensions == ["Account", "Entity"]
    assert a.counts == {
        "members": 4,
        "variables": 2,
        "userVariables": 2,
        "formsReferenced": 1,
        "dashboardsReferenced": 1,
        "rules": 1,
        "templates": 1,
        "integrations": 3,
        "pipelines": 1,
        "securityGroups": 2,
        "users": 3,
    }
    assert a.issues == []
    products = {c.product for c in a.components}
    assert products == {"HP", "CALC", "AIF", "HUB"}
    # every snapshot record is provenance-tagged
    assert all(r["data"].get("source") == "snapshot" for r in bundle.records)
    # no user emails/logins are ever stored
    assert not any("a@x.com" in str(r) for r in bundle.records)


def test_analyze_provenance_and_summary():
    bundle = analyze_snapshot(_make_snapshot_zip())
    prov = bundle.analysis.provenance
    assert prov is not None
    assert prov.exported_by == "cloud_admin"
    assert prov.exported_at == "2026-07-18T09:30Z"
    assert prov.service_instance == "acme-test"
    assert prov.domain == "acme2026"
    assert prov.exported_version == "26.07.95"
    text = summarize_snapshot(bundle.analysis)
    assert "ACME_PLN" in text and "4 members" in text and "exported" in text


def test_analyze_rule_bodies_prompts_and_templates():
    bundle = analyze_snapshot(_make_snapshot_zip())
    rule = next(r for r in bundle.records if r["kind"] == "rule")
    assert rule["name"] == "Calc All"
    assert rule["cube"] == "Plan1"
    data = rule["data"]
    assert data["scriptType"] == "groovy"
    assert data["runtimePrompts"] == ["RTP_Entity", "RTP_Version"]
    assert data["templates"] == ["Util_GT"]
    assert "if (x < 2)" in data["body"]  # XML entities unescaped
    template = next(r for r in bundle.records if r["kind"] == "template")
    assert template["name"] == "Util_GT" and template["cube"] == "Plan1"
    sections = {s.name: s for s in bundle.sections}
    assert sections["Rule Bodies & Runtime Prompts"].status == "complete"
    assert sections["Forms"].status == "derived"
    assert sections["Forms"].note == snapshot_mod._FORMS_REFERENCED_NOTE


def test_analyze_variables_and_integrations():
    bundle = analyze_snapshot(_make_snapshot_zip())
    variables = {r["name"]: r["data"] for r in bundle.records if r["kind"] == "variable"}
    assert variables["CurYr"]["value"] == "FY26" and variables["CurYr"]["cube"] is None
    assert variables["CashStart"]["cube"] == "Plan1"
    assert variables["UV_Entity"]["scope"] == "user" and variables["UV_Entity"]["dimension"] == "Entity"
    integrations = {r["name"]: r["data"] for r in bundle.records if r["kind"] == "integration"}
    assert integrations["DATA_DAILY"]["type"] == "importFormat"
    assert integrations["LOC_DAILY"]["type"] == "location"
    assert integrations["DAILY_PIPE"]["type"] == "pipeline" and integrations["DAILY_PIPE"]["stages"] == 2
    groups = sorted(r["name"] for r in bundle.records if r["kind"] == "securityGroup")
    assert groups == ["Admins", "Planners"]


def test_analyze_tolerates_wrapping_root_directory():
    bundle = analyze_snapshot(_make_snapshot_zip(prefix="Artifact Snapshot/"))
    assert bundle.analysis.application == "ACME_PLN"
    assert bundle.analysis.counts["members"] == 4


def test_analyze_detects_app_from_folder_when_export_missing():
    data = _make_snapshot_zip(**{"Export.xml": None, "Import.xml": None})
    bundle = analyze_snapshot(data)
    a = bundle.analysis
    assert a.application == "ACME_PLN"
    assert a.provenance is None
    fdmee = next(c for c in a.components if c.key.startswith("FDMEE-"))
    assert fdmee.product == "AIF"
    hss = next(c for c in a.components if c.key.startswith("HSS-"))
    assert hss.product == "HUB"


def test_rejects_non_zip():
    with pytest.raises(SnapshotError):
        analyze_snapshot(b"definitely not a zip archive")


def test_rejects_empty_or_structureless_zip():
    with pytest.raises(SnapshotError):
        analyze_snapshot(_zip_bytes({}))
    with pytest.raises(SnapshotError):
        analyze_snapshot(_zip_bytes({"random/notes.txt": "hello"}))


def test_zip_slip_entries_are_skipped_not_extracted():
    data = _make_snapshot_zip(**{
        "../evil.csv": "Account, Parent\nHacked,",
        "/abs/evil2.csv": "Account, Parent\nHacked2,",
    })
    bundle = analyze_snapshot(data)
    unsafe = [i for i in bundle.analysis.issues if "unsafe path" in i]
    assert len(unsafe) == 2
    assert not any(r["name"].startswith("Hacked") for r in bundle.records)
    assert bundle.analysis.application == "ACME_PLN"


def test_size_caps_reject_oversized_archives(monkeypatch):
    data = _make_snapshot_zip()
    monkeypatch.setattr(snapshot_mod, "_MAX_TOTAL_UNCOMPRESSED", 64)
    with pytest.raises(SnapshotError):
        analyze_snapshot(data)
    monkeypatch.undo()
    monkeypatch.setattr(snapshot_mod, "_MAX_ENTRIES", 3)
    with pytest.raises(SnapshotError):
        analyze_snapshot(data)


def test_oversized_entries_are_skipped_per_entry(monkeypatch):
    monkeypatch.setattr(snapshot_mod, "_MAX_TEXT_ENTRY", 32)
    bundle = analyze_snapshot(_make_snapshot_zip())
    assert any("oversized entry" in i for i in bundle.analysis.issues)
    assert bundle.analysis.application == "ACME_PLN"  # detection still works from folder names


def test_malformed_xml_is_an_issue_not_fatal():
    data = _make_snapshot_zip(**{
        "HP-ACME_PLN/resource/Global Artifacts/Substitution Variables/CurYr.xml":
            "<substitutionVariable><name>Broken",
    })
    bundle = analyze_snapshot(data)
    assert any("CurYr.xml" in i for i in bundle.analysis.issues)
    # everything else still parsed
    assert bundle.analysis.counts["members"] == 4
    assert bundle.analysis.counts["rules"] == 1
    assert "CashStart" in {r["name"] for r in bundle.records if r["kind"] == "variable"}


# --- merge ------------------------------------------------------------------------


async def test_merge_onto_active_context_is_hybrid(session):
    proj = projects_svc.create_project(session, "SnapMerge")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                  live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()

    # snapshot app MCW_PCF matches live MCWPCF after normalization
    bundle = analyze_snapshot(_make_snapshot_zip(app_name="MCW_PCF"), filename="snap.zip")
    cv = merge_snapshot_into_context(session, proj.id, bundle)
    session.flush()

    assert cv.mode == "hybrid"
    assert cv.active is True
    assert cv.application == "MCWPCF"
    assert cv.label == "MCWPCF_hybrid_1"

    # same-key snapshot member replaced the live one and adopted the live app name
    members = context_store.get_records(session, cv.id, kind="member")
    salaries = [r for r in members if r.name == "Salaries" and r.dimension == "Account"]
    assert len(salaries) == 1
    assert salaries[0].data["source"] == "snapshot"
    assert salaries[0].alias == "Snapshot Salaries"
    assert salaries[0].application == "MCWPCF"
    # live-only members are retained
    assert any(r.name == "Total Payroll" for r in members)

    # snapshot-only kinds are unioned in
    rules = context_store.get_records(session, cv.id, kind="rule")
    assert any(r.name == "Calc All" and r.data.get("body") for r in rules)
    assert context_store.get_records(session, cv.id, kind="template")

    manifest = cv.manifest
    assert manifest["mode"] == "hybrid"
    assert manifest["contextVersion"] == cv.label
    assert manifest["snapshot"]["application"] == "MCW_PCF"
    sections = {s["name"]: s for s in manifest["sections"]}
    assert sections["Rule Bodies & Runtime Prompts"]["status"] == "complete"
    assert "Rule Bodies & Runtime Prompts" in manifest["mergedSections"]
    assert cv.counts["rules"] >= 1 and cv.counts["templates"] == 1
    assert cv.counts["users"] == 3


async def test_tenant_metadata_rebuilds_from_hybrid_context(session):
    # Snapshot records carry provenance keys the strict record models forbid;
    # the artifact engine must still be able to reconstruct TenantMetadata.
    proj = projects_svc.create_project(session, "SnapMetadata")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                  live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    cv = merge_snapshot_into_context(session, proj.id, analyze_snapshot(_make_snapshot_zip(app_name="MCW_PCF")))
    session.flush()

    md = context_store.build_tenant_metadata(session, cv.id)
    assert md.application == "MCWPCF"
    account_members = md.members.get("Account", {})
    assert account_members.get("salaries") is not None
    assert any(r.name == "Calc All" for r in md.rules.values()) or "Calc All" in md.rules


async def test_merge_never_mutates_previous_version(session):
    proj = projects_svc.create_project(session, "SnapImmutable")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    cv1 = context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                        live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    before = len(context_store.get_records(session, cv1.id))

    bundle = analyze_snapshot(_make_snapshot_zip(app_name="MCW_PCF"))
    cv2 = merge_snapshot_into_context(session, proj.id, bundle)
    session.flush()
    session.expire_all()

    assert cv2.id != cv1.id
    assert cv1.active is False and cv2.active is True
    assert len(context_store.get_records(session, cv1.id)) == before
    old_salaries = next(r for r in context_store.get_records(session, cv1.id, kind="member")
                        if r.name == "Salaries")
    assert old_salaries.alias == "Base Salaries"


def test_standalone_import_is_snapshot_mode(session):
    proj = projects_svc.create_project(session, "SnapAlone")
    bundle = analyze_snapshot(_make_snapshot_zip())
    cv = merge_snapshot_into_context(session, proj.id, bundle, standalone=True, filename="acme.zip")
    session.flush()

    assert cv.mode == "snapshot"
    assert cv.active is True
    assert cv.application == "ACME_PLN"
    assert cv.label == "ACME_PLN_snapshot_1"
    assert cv.manifest["snapshot"]["filename"] == "acme.zip"
    assert cv.counts["members"] == 4
    assert cv.counts["dimensions"] == 2
    assert cv.counts["userVariables"] == 2
    sections = {s["name"]: s for s in cv.manifest["sections"]}
    assert sections["Dimensions"]["status"] == "complete"
    assert "mergedSections" not in cv.manifest


def test_merge_without_active_context_falls_back_to_snapshot_mode(session):
    proj = projects_svc.create_project(session, "SnapNoActive")
    bundle = analyze_snapshot(_make_snapshot_zip())
    cv = merge_snapshot_into_context(session, proj.id, bundle)
    session.flush()
    assert cv.mode == "snapshot"
    assert cv.label == "ACME_PLN_snapshot_1"


# --- real fixture -------------------------------------------------------------------


async def test_referenced_form_stub_never_replaces_live_definition(session):
    # A navigation-flow form *reference* must not clobber a live form record
    # that carries a real definition — stubs only fill gaps.
    proj = projects_svc.create_project(session, "SnapFormStub")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                  live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    live_form = next(r["name"] for r in live.records if r["kind"] == "form")

    files = _snapshot_files("MCW_PCF")
    files["HP-MCW_PCF/resource/Global Artifacts/Navigation Flows/Admin.xml"] = \
        _NAV_FLOW.replace("Rolling Forecast", live_form)
    cv = merge_snapshot_into_context(session, proj.id, analyze_snapshot(_zip_bytes(files)))
    session.flush()

    forms = [r for r in context_store.get_records(session, cv.id, kind="form") if r.name == live_form]
    assert len(forms) == 1
    assert not (forms[0].data or {}).get("referencedOnly")
    assert (forms[0].data or {}).get("source") != "snapshot"


async def test_application_record_deduped_after_normalized_match(session):
    proj = projects_svc.create_project(session, "SnapAppDedup")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                  live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    cv = merge_snapshot_into_context(session, proj.id, analyze_snapshot(_make_snapshot_zip(app_name="MCW_PCF")))
    session.flush()

    apps = context_store.get_records(session, cv.id, kind="application")
    assert [a.name for a in apps] == ["MCWPCF"]
    assert cv.counts["applications"] == 1


def test_record_cap_rejects_amplified_archives(monkeypatch):
    monkeypatch.setattr(snapshot_mod, "_MAX_RECORDS", 1)
    with pytest.raises(SnapshotError, match="record cap"):
        analyze_snapshot(_make_snapshot_zip())


def test_oversized_csv_field_is_an_issue_not_a_crash():
    files = _snapshot_files("ACME_PLN")
    files["HP-ACME_PLN/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Big.csv"] = \
        _dim_csv("Big", ["Big,,,,,,,,,,", '"' + "x" * 200_000 + '",Big,,,,,,,,,'])
    bundle = analyze_snapshot(_zip_bytes(files))
    assert bundle.analysis.application == "ACME_PLN"
    assert any("Big.csv" in i for i in bundle.analysis.issues)
    # the other dimensions still parsed
    assert "Account" in bundle.analysis.dimensions


async def test_epwcontext_roundtrip_keeps_snapshot_kinds(session):
    from app.context.package import export_context_package, import_context_package

    proj = projects_svc.create_project(session, "SnapRoundtrip")
    live = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    context_store.persist_context(session, proj.id, live.application, live.mode, live.label,
                                  live.manifest.model_dump(by_alias=True), live.counts, live.records)
    session.flush()
    cv = merge_snapshot_into_context(session, proj.id, analyze_snapshot(_make_snapshot_zip(app_name="MCW_PCF")))
    session.flush()

    _filename, data = export_context_package(session, cv.id)
    kinds = {r["kind"] for r in import_context_package(data).records}
    assert {"template", "integration", "securityGroup"} <= kinds


async def test_read_limited_caps_request_bodies():
    from fastapi import HTTPException, UploadFile

    from app.api.routes_context import _read_limited

    small = UploadFile(filename="ok.zip", file=io.BytesIO(b"x" * 1024))
    assert await _read_limited(small, limit=2048) == b"x" * 1024
    big = UploadFile(filename="big.zip", file=io.BytesIO(b"x" * (3 * 1024 * 1024)))
    with pytest.raises(HTTPException) as exc:
        await _read_limited(big, limit=1024 * 1024)
    assert exc.value.status_code == 413


def test_real_fixture_subset_parses():
    if not _FIXTURE.is_dir():
        pytest.skip("Artifact Snapshot fixture not present")
    wanted = [
        "Export.xml",
        "Import.xml",
        "HP-MCW_PCF/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Version.csv",
        "HP-MCW_PCF/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Currency.csv",
        "HP-MCW_PCF/resource/Global Artifacts/Substitution Variables/PlanStartYr.xml",
        "CALC-Calculation Manager/resource/Planning/MCW_PCF/OEP_DCSH/Rules/OCF_Daily Rollup Entity",
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in wanted:
            path = _FIXTURE / rel
            if not path.is_file():
                pytest.skip(f"fixture file missing: {rel}")
            zf.writestr(rel, path.read_bytes())

    bundle = analyze_snapshot(buf.getvalue(), filename="Artifact Snapshot.zip")
    a = bundle.analysis
    assert a.application == "MCW_PCF"
    assert "Version" in a.dimensions and "Currency" in a.dimensions
    assert a.counts["members"] > 0
    assert a.provenance is not None and a.provenance.exported_by == "epm_default_cloud_admin"

    rule = next(r for r in bundle.records if r["kind"] == "rule" and r["name"] == "OCF_Daily Rollup Entity")
    assert rule["data"]["scriptType"] == "groovy"
    assert rule["data"]["cube"] == "OEP_DCSH"
    assert "OCF_Currency" in rule["data"]["runtimePrompts"]
    assert "OCF_Forecast Utils_GT" in rule["data"]["templates"]

    variables = {r["name"]: r["data"] for r in bundle.records if r["kind"] == "variable"}
    assert variables["PlanStartYr"]["value"] == "FY25"
