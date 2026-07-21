"""Adversarial upload / endpoint robustness tests (Agent T5).

Contract under test:
  * No endpoint returns 500 on malformed / hostile input (400/404/413/422 only).
  * Uploads are size-, type- and path-safe; safe_filename neutralizes traversal,
    absolute paths, null bytes, over-long and unicode/emoji names.
  * The stored deterministic analysis survives a corrupt / missing cache and a
    missing source file without crashing.
  * Redaction holds: a credential embedded in file content OR filename never
    reaches the stored text_extract.

These tests exercise the HTTP surface through TestClient. A dedicated client with
``raise_server_exceptions=False`` is used so a server-side 500 is observable as a
status code (and asserted against) instead of aborting the test run.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from openpyxl import Workbook

from app.db.models import Attachment
from app.services import attachments as attachments_svc

XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- fixtures / helpers ------------------------------------------------------


@pytest.fixture
def raw_client():
    """TestClient that surfaces 500s as responses instead of re-raising, so we
    can assert 'this route must never 500'."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _pid_cid(client) -> tuple[str, str]:
    pid = client.post("/api/projects", json={"name": "fuzz"}).json()["id"]
    cid = client.post(f"/api/projects/{pid}/conversations", json={"title": "t"}).json()["id"]
    return pid, cid


def _xlsx(rows: list[list] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Accounts"
    for row in rows or [["Account", "Parent"], ["Total Payroll", ""]]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _snapshot_zip(app_name: str = "FUZZ_APP") -> bytes:
    """A minimal but real LCM snapshot the deterministic analyzer accepts."""
    hp = f"HP-{app_name}"
    export_xml = (
        '<?xml version="1.0" encoding="UTF-8"?><Package><LOCALE>en_US</LOCALE>'
        '<User name="" password=""/><Task>'
        f'<Source type="Application" product="HP" project="Default Application Group" application="{app_name}"/>'
        f'<Target type="FileSystem" filePath="/{hp}"/>'
        '<Artifact recursive="true" parentPath="/" pattern="*"/></Task></Package>'
    )
    import_xml = (
        '<?xml version="1.0" encoding="UTF-8"?><Package><LOCALE>en_US</LOCALE>'
        '<User name="" password=""/><Task>'
        f'<Source type="FileSystem" filePath="/{hp}"/>'
        f'<Target type="Application" product="HP" project="Default Application Group" application="{app_name}"/>'
        '<Artifact recursive="true" parentPath="/" pattern="*"/></Task></Package>'
    )
    listing = (
        '<?xml version="1.0" encoding="utf-8"?><artifactListing><resource name="Account" '
        'id="Account" type="Planning Dimension" cloneOnly="false" size="" '
        'path="/Global Artifacts/Common Dimensions/Standard Dimensions" pathAlias="" '
        'modifiedBy="" lastUpdated="" description="" /></artifactListing>'
    )
    account_csv = (
        "﻿#!-- HEADERBLOCK DIMENSION XML\n"
        '<?xml version="1.0" encoding="UTF-8" ?>\n<DIMENSIONS>\n'
        ' <Dimension name="Account" origname="Account" dimensionType="Accounts" '
        'density="Dense" DimensionAlias="Account" />\n</DIMENSIONS>\n#--!\n'
        "Account, Parent, Alias: Default, Data Storage, Formula, Data Type\n"
        "Total Payroll,,Payroll Costs,store,,currency\n"
        "Salaries,Total Payroll,,store,,currency\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Export.xml", export_xml)
        zf.writestr("Import.xml", import_xml)
        zf.writestr(f"{hp}/Import.xml", import_xml)
        zf.writestr(f"{hp}/info/listing.xml", listing)
        zf.writestr(
            f"{hp}/resource/Global Artifacts/Common Dimensions/Standard Dimensions/Account.csv",
            account_csv,
        )
    return buf.getvalue()


def _upload(client, cid: str, filename: str, data: bytes, content_type: str):
    return client.post(
        f"/api/conversations/{cid}/attachments",
        files={"file": (filename, data, content_type)},
    )


# --- upload: missing / empty / malformed multipart ---------------------------


def test_upload_no_file_field_is_422(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = raw_client.post(f"/api/conversations/{cid}/attachments")
    assert r.status_code == 422


def test_upload_empty_file_is_400(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "empty.xlsx", b"", XLSX_CT)
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_upload_zero_byte_csv_is_400(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "empty.csv", b"", "text/csv")
    assert r.status_code == 400


def test_upload_wrong_extension_is_400(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "notes.txt", b"hello world", "text/plain")
    assert r.status_code == 400
    assert "unsupported" in r.json()["detail"].lower()


def test_upload_no_extension_is_400_not_500(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "noext", _xlsx(), XLSX_CT)
    assert r.status_code == 400


def test_upload_content_type_is_ignored_extension_wins(raw_client):
    """A real .xlsx sent with a bogus content-type still uploads (200-family);
    a .txt sent as spreadsheet content-type is still rejected."""
    _pid, cid = _pid_cid(raw_client)
    assert _upload(raw_client, cid, "coa.xlsx", _xlsx(), "application/octet-stream").status_code == 201
    assert _upload(raw_client, cid, "coa.xlsx", _xlsx(), "text/plain").status_code == 201
    assert _upload(raw_client, cid, "evil.txt", _xlsx(), XLSX_CT).status_code == 400


# --- upload: hostile filenames ----------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "../../../etc/passwd.xlsx",
        "/absolute/path/book.xlsx",
        "..\\..\\windows\\book.xlsx",
        "....//....//book.xlsx",
        "a" * 400 + ".xlsx",            # over-long -> ENAMETOOLONG guard
        "emoji_\U0001F600\U0001F389.xlsx",
        "unícode_ñåme.xlsx",
        "con.xlsx",                     # windows reserved
        "file\twith\ttabs.xlsx",
        "spaces   and...dots.xlsx",
    ],
)
def test_hostile_filenames_upload_safely(raw_client, filename):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, filename, _xlsx(), XLSX_CT)
    assert r.status_code == 201, (filename, r.status_code)
    stored = r.json()["filename"]
    # no path escape, no separators, no traversal survive
    assert "/" not in stored and "\\" not in stored
    assert ".." not in stored
    assert not stored.startswith("/")
    assert len(stored) <= 130  # length-bounded so the on-disk write is safe


def test_null_byte_filename_does_not_crash(raw_client):
    _pid, cid = _pid_cid(raw_client)
    # a null in the stem is scrubbed to '_' (valid .xlsx ext survives)
    r = _upload(raw_client, cid, "evil\x00name.xlsx", _xlsx(), "application/octet-stream")
    assert r.status_code == 201
    assert "\x00" not in r.json()["filename"]
    # a null inside the extension makes the ext invalid -> 400, never 500
    r2 = _upload(raw_client, cid, "evil.xl\x00sx", _xlsx(), "application/octet-stream")
    assert r2.status_code == 400


def test_safe_filename_unit_neutralizes_and_bounds():
    f = attachments_svc.safe_filename
    assert f("../../etc/passwd.xlsx") == "passwd.xlsx"
    assert f("/abs/book.CSV") == "book.csv"
    assert f("..\\..\\win.zip") == "win.zip"
    assert "/" not in f("a/b/c.xlsx") and "\\" not in f("a\\b.xlsx")
    assert ".." not in f("....xlsx")
    assert f("") == "upload"
    assert f("   .xlsx").endswith(".xlsx")
    long = f("z" * 500 + ".xlsx")
    assert len(long) <= 130 and long.endswith(".xlsx")
    # a pathologically long "extension" is folded back into the stem, not written
    huge_ext = f("name." + "e" * 400)
    assert len(huge_ext) <= 130


# --- upload: type confusion (zip<->spreadsheet) ------------------------------


def test_zip_that_is_actually_a_spreadsheet_is_rejected(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "sheet.zip", _xlsx(), "application/zip")
    assert r.status_code == 400  # not a valid LCM snapshot


def test_spreadsheet_that_is_actually_a_snapshot_zip_is_rejected(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "snap.xlsx", _snapshot_zip(), XLSX_CT)
    assert r.status_code == 400  # openpyxl rejects a non-workbook zip


def test_garbage_xlsx_is_400(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "garbage.xlsx", b"\x00\x01\x02 not a real workbook", XLSX_CT)
    assert r.status_code == 400
    assert "could not parse" in r.json()["detail"].lower()


def test_bogus_zip_is_400(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r = _upload(raw_client, cid, "bogus.zip", b"this is not a zip archive at all", "application/zip")
    assert r.status_code == 400


# --- upload: size caps -------------------------------------------------------


def test_spreadsheet_size_cap_boundary(raw_client, monkeypatch):
    """At the cap uploads; one byte over is a clean 400 (never 500), with a
    helpful message. Cap is shrunk via monkeypatch so no large allocation."""
    _pid, cid = _pid_cid(raw_client)
    data = _xlsx()
    n = len(data)
    monkeypatch.setattr(attachments_svc, "MAX_SIZE_BYTES", n)
    assert _upload(raw_client, cid, "at_cap.xlsx", data, XLSX_CT).status_code == 201
    monkeypatch.setattr(attachments_svc, "MAX_SIZE_BYTES", n - 1)
    r = _upload(raw_client, cid, "over_cap.xlsx", data, XLSX_CT)
    assert r.status_code == 400
    assert "limit" in r.json()["detail"].lower()


def test_zip_size_cap_boundary(raw_client, monkeypatch):
    """The 200 MB snapshot cap is shrunk to the payload size so we exercise the
    boundary without allocating anything large."""
    _pid, cid = _pid_cid(raw_client)
    data = _snapshot_zip()
    n = len(data)
    monkeypatch.setattr(attachments_svc, "ZIP_MAX_SIZE_BYTES", n)
    assert _upload(raw_client, cid, "at_cap.zip", data, "application/zip").status_code == 201
    monkeypatch.setattr(attachments_svc, "ZIP_MAX_SIZE_BYTES", n - 1)
    r = _upload(raw_client, cid, "over_cap.zip", data, "application/zip")
    assert r.status_code == 400
    assert "limit" in r.json()["detail"].lower()


async def test_read_limited_returns_413_over_limit():
    """The chunked body reader caps memory and raises 413, not a 500 or OOM."""
    from fastapi import HTTPException
    from starlette.datastructures import UploadFile

    from app.api.routes_context import _read_limited

    upload = UploadFile(filename="big.zip", file=io.BytesIO(b"x" * 5000))
    with pytest.raises(HTTPException) as ei:
        await _read_limited(upload, limit=1000)
    assert ei.value.status_code == 413


# --- upload: duplicates / unknown conversation -------------------------------


def test_duplicate_uploads_do_not_collide(raw_client):
    _pid, cid = _pid_cid(raw_client)
    r1 = _upload(raw_client, cid, "coa.xlsx", _xlsx(), XLSX_CT)
    r2 = _upload(raw_client, cid, "coa.xlsx", _xlsx(), XLSX_CT)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]  # distinct storage dirs, no crash


def test_upload_to_unknown_conversation_is_404(raw_client):
    r = _upload(raw_client, "no-such-conversation", "coa.xlsx", _xlsx(), XLSX_CT)
    assert r.status_code == 404


# --- analysis endpoint: missing / corrupt on-disk state ----------------------


def _attachment_dir(att_id: str):
    import pathlib

    from app.db.base import get_sessionmaker

    s = get_sessionmaker()()
    try:
        att = attachments_svc.get_attachment(s, att_id)
        return pathlib.Path(att.path).parent
    finally:
        s.close()


def test_spreadsheet_analysis_survives_corrupt_cache(raw_client):
    """A corrupt analysis.json must not 500 — re-parse from the source file."""
    _pid, cid = _pid_cid(raw_client)
    att_id = _upload(raw_client, cid, "coa.xlsx", _xlsx(), XLSX_CT).json()["id"]
    (_attachment_dir(att_id) / "analysis.json").write_text("{ not valid json ]")
    r = raw_client.get(f"/api/attachments/{att_id}/analysis")
    assert r.status_code == 200  # fell back to a fresh parse


def test_spreadsheet_analysis_missing_source_is_404_not_500(raw_client):
    _pid, cid = _pid_cid(raw_client)
    att_id = _upload(raw_client, cid, "coa.xlsx", _xlsx(), XLSX_CT).json()["id"]
    for p in _attachment_dir(att_id).iterdir():
        p.unlink()
    assert raw_client.get(f"/api/attachments/{att_id}/analysis").status_code == 404
    assert raw_client.get(f"/api/attachments/{att_id}").status_code == 404


def test_snapshot_analysis_survives_corrupt_cache(raw_client):
    _pid, cid = _pid_cid(raw_client)
    att_id = _upload(raw_client, cid, "snap.zip", _snapshot_zip(), "application/zip").json()["id"]
    (_attachment_dir(att_id) / "snapshot.json").write_text("garbage {{{ not json")
    r = raw_client.get(f"/api/attachments/{att_id}/analysis")
    assert r.status_code == 200  # re-parsed the zip in-memory


def test_snapshot_analysis_missing_source_is_404_not_500(raw_client):
    _pid, cid = _pid_cid(raw_client)
    att_id = _upload(raw_client, cid, "snap.zip", _snapshot_zip(), "application/zip").json()["id"]
    for p in _attachment_dir(att_id).iterdir():
        p.unlink()
    assert raw_client.get(f"/api/attachments/{att_id}/analysis").status_code == 404


def test_analysis_of_unknown_attachment_is_404(raw_client):
    assert raw_client.get("/api/attachments/nope/analysis").status_code == 404
    assert raw_client.get("/api/attachments/nope").status_code == 404


# --- redaction ---------------------------------------------------------------


def test_credential_in_cell_is_redacted_in_text_extract(raw_client, session):
    _pid, cid = _pid_cid(raw_client)
    rows = [["Account", "Parent", "sk-ant-api03-VERYSECRETKEY1234567890"],
            ["Total Payroll", "", ""]]
    att_id = _upload(raw_client, cid, "coa.xlsx", _xlsx(rows), XLSX_CT).json()["id"]
    session.expire_all()
    att = session.get(Attachment, att_id)
    assert "VERYSECRETKEY1234567890" not in att.text_extract
    assert "«redacted»" in att.text_extract


def test_credential_in_filename_is_redacted_in_text_extract(raw_client, session):
    """safe_filename rewrites '=' to '_', which would defeat the password=<value>
    pattern; the ORIGINAL filename is redacted so the secret never lands."""
    _pid, cid = _pid_cid(raw_client)
    att_id = _upload(raw_client, cid, "password=Hunter2SecretValue.xlsx", _xlsx(), XLSX_CT).json()["id"]
    session.expire_all()
    att = session.get(Attachment, att_id)
    assert "Hunter2SecretValue" not in att.text_extract


# --- general endpoint fuzzing (report-only for non-owned routes; assert !=500) --


def test_message_endpoint_malformed_bodies_never_500(raw_client):
    _pid, cid = _pid_cid(raw_client)
    ep = f"/api/conversations/{cid}/messages"
    cases = [
        {"content": 123},
        {"content": None},
        {},
        {"content": "hi", "attachments": "not-a-list"},
        {"content": "hi", "attachments": [1, 2, 3]},
        {"content": "hi", "attachments": ["unknown-attachment-id"]},
        {"content": "hi", "bogus_extra": {"a": 1}},
        {"content": "A" * 500_000},
    ]
    for body in cases:
        r = raw_client.post(ep, json=body)
        assert r.status_code != 500, (body, r.status_code)
    # non-JSON and array bodies
    assert raw_client.post(ep, content=b"not json", headers={"Content-Type": "application/json"}).status_code != 500
    assert raw_client.post(ep, json=[1, 2, 3]).status_code != 500


def test_project_and_conversation_create_malformed_never_500(raw_client):
    for body in [{}, {"name": 123}, {"name": None}, {"name": ["a"]}, {"name": "A" * 200_000}]:
        assert raw_client.post("/api/projects", json=body).status_code != 500, body
    pid = raw_client.post("/api/projects", json={"name": "ok"}).json()["id"]
    for body in [{"title": 123}, {"title": ["x"]}, {"unexpected": 1}]:
        assert raw_client.post(f"/api/projects/{pid}/conversations", json=body).status_code != 500, body


@pytest.mark.parametrize(
    "path_param",
    ["nope", "\U0001F600", "'; DROP TABLE projects;--", "../../etc/passwd", "%00", "x" * 4000],
)
def test_path_params_hostile_ids_never_500(raw_client, path_param):
    for url in (
        f"/api/projects/{path_param}",
        f"/api/attachments/{path_param}",
        f"/api/attachments/{path_param}/analysis",
        f"/api/artifacts/{path_param}",
        f"/api/conversations/{path_param}/messages",
    ):
        assert raw_client.get(url).status_code != 500, url


def test_query_param_extremes_never_500(raw_client):
    pid = raw_client.post("/api/projects", json={"name": "q"}).json()["id"]
    raw_client.post(f"/api/projects/{pid}/contexts/build")
    checks = [
        (f"/api/projects/{pid}/search", {"q": "x", "limit": -1}),
        (f"/api/projects/{pid}/search", {"q": "x", "limit": 10 ** 12}),
        (f"/api/projects/{pid}/context/search", {"q": "x", "limit": -5}),
        (f"/api/projects/{pid}/context/search", {"q": "\U0001F600'; DROP TABLE members;--"}),
        (f"/api/projects/{pid}/artifacts", {"kind": "'; DROP--"}),
        (f"/api/projects/{pid}/rule-executions", {"rule_name": "\U0001F600"}),
        (f"/api/projects/{pid}/deployments", {"success": "maybe"}),
        (f"/api/projects/{pid}/impact", {"member": "\U0001F600"}),
    ]
    for url, params in checks:
        assert raw_client.get(url, params=params).status_code != 500, (url, params)


def test_import_and_snapshot_routes_reject_garbage_not_500(raw_client):
    pid = raw_client.post("/api/projects", json={"name": "imp"}).json()["id"]
    assert raw_client.post("/api/projects/import",
                           files={"file": ("x.zip", b"not a zip", "application/zip")}).status_code == 400
    assert raw_client.post(f"/api/projects/{pid}/contexts/import",
                           files={"file": ("x.epwcontext", b"garbage", "application/octet-stream")}).status_code == 400
    assert raw_client.post(f"/api/projects/{pid}/contexts/snapshot",
                           files={"file": ("x.zip", b"not a zip", "application/zip")}).status_code == 400
    # unknown project -> 404, never 500
    assert raw_client.post("/api/projects/nope/contexts/snapshot",
                           files={"file": ("x.zip", _snapshot_zip(), "application/zip")}).status_code == 404


def test_build_context_bad_mode_is_422_not_500(raw_client):
    """FIXED (routes_context.py): POST /contexts/build?mode=<garbage> used to
    pass the unvalidated mode straight into the ContextManifest enum, raising a
    ValidationError -> HTTP 500. The route now validates mode in {quick, deep}
    and 422s otherwise; the two real build depths still succeed."""
    pid = raw_client.post("/api/projects", json={"name": "mode"}).json()["id"]
    r = raw_client.post(f"/api/projects/{pid}/contexts/build", params={"mode": "bogus-mode"})
    assert r.status_code == 422, r.text
    for good in ("quick", "deep"):
        assert raw_client.post(
            f"/api/projects/{pid}/contexts/build", params={"mode": good}).status_code == 200
