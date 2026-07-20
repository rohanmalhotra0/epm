"""Snapshot chat + API flow tests: end-to-end over the HTTP API (upload an LCM
snapshot zip -> chat routes to the context skill -> merge/standalone import),
plus the direct POST /contexts/snapshot route.

The zip is synthesized in-memory with a dynamic application name so nothing is
hardcoded and the repo's "Artifact Snapshot" fixture folder is never required.
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from app.services import context_store

# --- helpers -----------------------------------------------------------------


def _new_project_conversation(client, name: str) -> tuple[str, str]:
    pid = client.post("/api/projects", json={"name": name}).json()["id"]
    cid = client.post(f"/api/projects/{pid}/conversations", json={"title": "Snapshot drop"}).json()["id"]
    return pid, cid


def _upload_zip(client, cid: str, data: bytes, filename: str = "snapshot.zip"):
    return client.post(f"/api/conversations/{cid}/attachments",
                       files={"file": (filename, data, "application/zip")})


def _send(client, cid: str, text: str, attachments: list[str] | None = None) -> str:
    body: dict = {"content": text}
    if attachments:
        body["attachments"] = attachments
    return client.post(f"/api/conversations/{cid}/messages", json=body).text


def _events(sse_text: str) -> list[tuple[str, dict]]:
    return [(m.group(1), json.loads(m.group(2)))
            for m in re.finditer(r"event: (\w+)\ndata: (.*?)\n\n", sse_text, re.S)]


def _blocks(sse_text: str) -> list[dict]:
    return [data for name, data in _events(sse_text) if name == "block"]


def _block_types(sse_text: str) -> list[str]:
    return [b["type"] for b in _blocks(sse_text)]


def _first_block(sse_text: str, block_type: str) -> dict:
    return next(b for b in _blocks(sse_text) if b["type"] == block_type)


def _markdown_text(sse_text: str) -> str:
    return "\n".join(b["data"].get("text", "") for b in _blocks(sse_text) if b["type"] == "markdown")


def _action_values(sse_text: str) -> list[str]:
    return [a["value"] for b in _blocks(sse_text) if b["type"] == "confirmation"
            for a in b["data"]["actions"]]


# --- synthetic LCM snapshot zip ------------------------------------------------


def _dimension_csv(dimension: str, rows: list[tuple[str, str]]) -> str:
    """The real LCM dimension format: BOM + HEADERBLOCK XML + '#--!' sentinel +
    a CSV whose first column is named after the dimension."""
    lines = [
        "\ufeff#!-- HEADERBLOCK DIMENSION XML",
        '<?xml version="1.0" encoding="UTF-8" ?>',
        "<DIMENSIONS>",
        f' <Dimension name="{dimension}" origname="{dimension}" dimensionType="Accounts" '
        f'density="Dense" DimensionAlias="{dimension}" />',
        "</DIMENSIONS>",
        "#--!",
        f"{dimension}, Parent, Alias: Default, Data Storage, Formula, Data Type",
        "Total Payroll,,Payroll Costs,store,,currency",
    ]
    lines += [f"{name},{parent},,store,,currency" for name, parent in rows]
    return "\n".join(lines) + "\n"


def _snapshot_zip(app_name: str = "ACME_PLN") -> bytes:
    hp = f"HP-{app_name}"
    export_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package>
   <LOCALE>en_US</LOCALE>
   <User name="" password=""/>
   <Task>
      <Source type="Application" product="HP" project="Default Application Group" application="{app_name}"/>
      <Target type="FileSystem" filePath="/{hp}"/>
      <Artifact recursive="true" parentPath="/" pattern="*"/>
   </Task>
</Package>
"""
    import_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package>
   <LOCALE>en_US</LOCALE>
   <User name="" password=""/>
   <ExportedVersion>26.07.95</ExportedVersion>
   <ExportedDateUTC>20260401</ExportedDateUTC>
   <ExportedTimeUTC>08:30</ExportedTimeUTC>
   <ExportedBy>synthetic_admin</ExportedBy>
   <IDMDomain>synthdom</IDMDomain>
   <ServiceInstance>synth-test</ServiceInstance>
   <Task>
      <Source type="FileSystem" filePath="/{hp}"/>
      <Target type="Application" product="HP" project="Default Application Group" application="{app_name}"/>
      <Artifact recursive="true" parentPath="/" pattern="*"/>
   </Task>
</Package>
"""
    listing_xml = ('<?xml version="1.0" encoding="utf-8"?><artifactListing>'
                   '<resource name="Account" id="Account" type="Planning Dimension" '
                   'cloneOnly="false" size="" path="/Global Artifacts/Common Dimensions/'
                   'Standard Dimensions" pathAlias="" modifiedBy="" lastUpdated="" description="" />'
                   "</artifactListing>")
    sub_var = ("""<?xml version="1.0" encoding="UTF-8" ?>
 <substitutionVariable>
 <name>CurYr</name>
 <value>FY26</value>
 <planType>ALL</planType>
</substitutionVariable>
""")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Export.xml", export_xml)
        zf.writestr("Import.xml", import_xml)
        zf.writestr(f"{hp}/Import.xml", import_xml)
        zf.writestr(f"{hp}/info/listing.xml", listing_xml)
        zf.writestr(
            f"{hp}/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Account.csv",
            _dimension_csv("Account", [("Salaries", "Total Payroll"),
                                       ("Rocket Thrusters", "Total Payroll")]))
        zf.writestr(f"{hp}/resource/Global Artifacts/Substitution Variables/CurYr.xml", sub_var)
    return buf.getvalue()


# --- attachment upload ---------------------------------------------------------


def test_zip_upload_is_analyzed_as_snapshot(client):
    _pid, cid = _new_project_conversation(client, "Snapshot Upload")
    r = _upload_zip(client, cid, _snapshot_zip(), "acme_snapshot.zip")
    assert r.status_code == 201
    body = r.json()
    assert body["kindGuess"] == "snapshot"
    assert body["sheetNames"] == []
    assert body["mediaType"] == "application/zip"

    # the stored analysis is served back (snapshot shape, not workbook shape)
    analysis = client.get(f"/api/attachments/{body['id']}/analysis").json()
    assert analysis["application"] == "ACME_PLN"
    assert "Account" in analysis["dimensions"]


def test_bad_zip_upload_is_rejected(client):
    _pid, cid = _new_project_conversation(client, "Snapshot Bad Zip")
    r = _upload_zip(client, cid, b"this is not a zip archive", "bogus.zip")
    assert r.status_code == 400


# --- chat flow: upload turn ------------------------------------------------------


def test_snapshot_message_with_active_context_offers_confirmation(client):
    pid, cid = _new_project_conversation(client, "Snapshot Confirm")
    assert client.post(f"/api/projects/{pid}/contexts/build").status_code == 200
    att_id = _upload_zip(client, cid, _snapshot_zip("ZED_FIN"), "zed.zip").json()["id"]

    sse = _send(client, cid, "here is our application snapshot", attachments=[att_id])
    types = _block_types(sse)
    assert "snapshotSummary" in types
    assert "confirmation" in types
    summary = _first_block(sse, "snapshotSummary")["data"]
    assert summary["application"] == "ZED_FIN"  # dynamic — read from the zip
    assert summary["filename"] == "zed.zip"

    # Action values are bound to the summarized attachment so a later zip
    # upload can never hijack a stale confirmation button.
    values = _action_values(sse)
    assert f"/context merge snapshot {att_id}" in values
    assert f"/context import snapshot {att_id}" in values
    assert "cancel" in values


def test_confirmation_acts_on_the_summarized_zip_not_the_newest(client, session):
    pid, cid = _new_project_conversation(client, "Snapshot Binding")
    assert client.post(f"/api/projects/{pid}/contexts/build").status_code == 200
    first_id = _upload_zip(client, cid, _snapshot_zip("ALPHA_APP"), "alpha.zip").json()["id"]
    sse = _send(client, cid, "snapshot attached", attachments=[first_id])
    merge_value = next(v for v in _action_values(sse) if v.startswith("/context merge snapshot"))
    # a second zip arrives later — the old confirmation must still merge alpha.zip
    second_id = _upload_zip(client, cid, _snapshot_zip("BETA_APP"), "beta.zip").json()["id"]
    _send(client, cid, "another snapshot", attachments=[second_id])

    _send(client, cid, merge_value)
    session.expire_all()
    cv = context_store.get_active_context(session, pid)
    assert cv is not None and cv.mode == "hybrid"
    assert (cv.manifest or {}).get("snapshot", {}).get("application") == "ALPHA_APP"


def test_snapshot_upload_without_context_imports_standalone(client, session):
    pid, cid = _new_project_conversation(client, "Snapshot Standalone Chat")
    att_id = _upload_zip(client, cid, _snapshot_zip(), "acme.zip").json()["id"]

    sse = _send(client, cid, "load this snapshot", attachments=[att_id])
    types = _block_types(sse)
    assert "snapshotSummary" in types
    assert "confirmation" not in types  # nothing to merge onto -> imported directly
    assert "contextSummary" in types

    session.expire_all()
    cv = context_store.get_active_context(session, pid)
    assert cv is not None
    assert cv.mode == "snapshot"
    assert cv.active is True


# --- chat flow: merge command ---------------------------------------------------


def test_merge_snapshot_creates_active_hybrid_version(client, session):
    pid, cid = _new_project_conversation(client, "Snapshot Merge")
    assert client.post(f"/api/projects/{pid}/contexts/build").status_code == 200
    att_id = _upload_zip(client, cid, _snapshot_zip(), "acme.zip").json()["id"]
    _send(client, cid, "snapshot attached", attachments=[att_id])

    sse = _send(client, cid, "/context merge snapshot")
    types = _block_types(sse)
    assert "contextSummary" in types
    assert "diff" in types  # before/after counts for merges
    assert "Sections upgraded by the snapshot" in _markdown_text(sse)

    session.expire_all()
    cv = context_store.get_active_context(session, pid)
    assert cv is not None
    assert cv.mode == "hybrid"
    assert cv.active is True
    members = {r.name: r for r in context_store.get_records(session, cv.id, kind="member")}
    assert "Rocket Thrusters" in members  # snapshot-only member landed
    assert (members["Rocket Thrusters"].data or {}).get("source") == "snapshot"


def test_merge_snapshot_without_zip_is_helpful(client):
    _pid, cid = _new_project_conversation(client, "Snapshot Missing")
    sse = _send(client, cid, "/context merge snapshot")
    md = _markdown_text(sse)
    assert "no snapshot zip" in md.lower()


# --- direct route ----------------------------------------------------------------


def test_snapshot_route_standalone_import(client):
    pid, _cid = _new_project_conversation(client, "Snapshot Route")
    r = client.post(f"/api/projects/{pid}/contexts/snapshot?standalone=true",
                    files={"file": ("acme.zip", _snapshot_zip(), "application/zip")})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "snapshot"
    assert body["active"] is True
    assert body["counts"].get("members", 0) >= 3

    listed = client.get(f"/api/projects/{pid}/contexts").json()
    assert any(cv["id"] == body["id"] for cv in listed)


def test_snapshot_route_merges_onto_active_context(client):
    pid, _cid = _new_project_conversation(client, "Snapshot Route Merge")
    assert client.post(f"/api/projects/{pid}/contexts/build").status_code == 200
    r = client.post(f"/api/projects/{pid}/contexts/snapshot",
                    files={"file": ("acme.zip", _snapshot_zip(), "application/zip")})
    assert r.status_code == 200
    assert r.json()["mode"] == "hybrid"


def test_snapshot_route_rejects_bad_zip_and_unknown_project(client):
    pid, _cid = _new_project_conversation(client, "Snapshot Route Bad")
    r = client.post(f"/api/projects/{pid}/contexts/snapshot",
                    files={"file": ("bogus.zip", b"not a zip", "application/zip")})
    assert r.status_code == 400

    r = client.post("/api/projects/nope/contexts/snapshot",
                    files={"file": ("acme.zip", _snapshot_zip(), "application/zip")})
    assert r.status_code == 404
