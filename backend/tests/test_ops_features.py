"""Tests for the ops/portability features: project export/import bundles,
SQLite backups + rotation, disk usage, impact analysis and EPM Automate
script export."""

from __future__ import annotations

import io
import json
import zipfile
from hashlib import sha256

import pytest

from app.config import get_settings
from app.db.models import (
    Artifact,
    ContextRecord,
    ContextVersion,
    Conversation,
    Deployment,
    EnvironmentProfile,
    Message,
    Project,
    RuleExecution,
)
from app.services import backups as backups_svc

FORM_PAYLOAD = {
    "schemaVersion": "1.0.0",
    "name": "Payroll Review",
    "application": "MCWPCF",
    "cube": "Plan1",
    "rows": [
        {"dimension": "Account",
         "selection": {"type": "levelZeroDescendants", "member": "Total Payroll"}},
    ],
    "columns": [
        {"dimension": "Period", "selection": {"type": "children", "member": "YearTotal"}},
    ],
}

RULE_PAYLOAD = {
    "schemaVersion": "1.0.0",
    "name": "Allocate Payroll",
    "application": "MCWPCF",
    "cube": "Plan1",
    "referencedMembers": ["Total Payroll", "Salaries"],
    "referencedDimensions": ["Account"],
}


def _seed_project(session) -> dict:
    """Create a project with one row in every exported child table."""
    settings = get_settings()
    project = Project(name="Bundle Source", description="seeded for tests")
    session.add(project)
    session.flush()

    env = EnvironmentProfile(project_id=project.id, name="Dev", base_url="https://example.test",
                             username="planner", classification="development", demo=True)
    session.add(env)

    conv = Conversation(project_id=project.id, title="Payroll chat")
    session.add(conv)
    session.flush()
    m1 = Message(conversation_id=conv.id, role="user", content="build a payroll form")
    session.add(m1)
    session.flush()
    m2 = Message(conversation_id=conv.id, role="assistant", content="done", parent_id=m1.id)
    session.add(m2)

    cv = ContextVersion(project_id=project.id, environment_id=env.id, application="MCWPCF",
                        label="Deep context", mode="deep", counts={"members": 1}, active=True)
    session.add(cv)
    session.flush()
    session.add(ContextRecord(context_version_id=cv.id, project_id=project.id, kind="member",
                              name="Total Payroll", dimension="Account", search_text="total payroll"))
    project.active_environment_id = env.id
    project.active_context_version_id = cv.id

    spec_art = Artifact(project_id=project.id, kind="formSpec", name="Payroll Review",
                        payload=FORM_PAYLOAD, context_version=cv.id)
    rule_art = Artifact(project_id=project.id, kind="ruleSpec", name="Allocate Payroll",
                        payload=RULE_PAYLOAD)
    session.add_all([spec_art, rule_art])

    pkg_bytes = b"PK-test-package-bytes"
    checksum = sha256(pkg_bytes).hexdigest()
    pkg_path = settings.artifacts_dir / f"Payroll_Review_{checksum[:12]}.zip"
    pkg_path.write_bytes(pkg_bytes)
    pkg_art = Artifact(project_id=project.id, kind="package", name="Payroll Review.zip",
                       path=str(pkg_path), checksum=checksum)
    session.add(pkg_art)
    session.flush()

    dep = Deployment(project_id=project.id, conversation_id=conv.id, environment_name="Dev",
                     classification="development", application="MCWPCF",
                     artifact_name="Payroll Review", artifact_type="planningForm",
                     operation="create", operation_class="modifying", approved=True,
                     checksum=checksum, success=True, verified=True, demo_mode=True)
    session.add(dep)
    session.add(RuleExecution(project_id=project.id, conversation_id=conv.id,
                              rule_name="Allocate Payroll", application="MCWPCF", cube="Plan1",
                              status="completed", prompt_values={"Scenario": "Actual"}))
    session.flush()
    session.commit()
    return {"project_id": project.id, "conversation_id": conv.id, "deployment_id": dep.id,
            "package_checksum": checksum, "package_filename": pkg_path.name}


# --- Export / import ---------------------------------------------------------


def test_export_bundle_shape(client, session):
    seeded = _seed_project(session)
    r = client.get(f"/api/projects/{seeded['project_id']}/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert "manifest.json" in names and "project.json" in names and "messages.json" in names
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["format"] == "epmwizard-project-bundle"
    assert manifest["bundleFormatVersion"] == "1.0.0"
    assert manifest["projectId"] == seeded["project_id"]
    assert manifest["exportedAt"]
    # every declared member is present with a correct checksum
    for name in manifest["files"]:
        assert sha256(zf.read(name)).hexdigest() == manifest["checksums"][name]
    # environments carry no secret material (no password-like keys at all)
    envs = json.loads(zf.read("environments.json"))
    assert envs and not any("password" in k.lower() or "secret" in k.lower()
                            for e in envs for k in e)


def test_export_import_round_trip(client, session):
    seeded = _seed_project(session)
    old_pid = seeded["project_id"]
    bundle = client.get(f"/api/projects/{old_pid}/export").content

    r = client.post("/api/projects/import",
                    files={"file": ("bundle.zip", bundle, "application/zip")})
    assert r.status_code == 201, r.text
    imported = r.json()
    new_pid = imported["id"]
    assert new_pid != old_pid
    assert imported["name"] == "Bundle Source"
    assert imported["isDefault"] is False

    # children exist under the new project with remapped foreign keys
    convs = client.get(f"/api/projects/{new_pid}/conversations").json()
    assert len(convs) == 1 and convs[0]["projectId"] == new_pid
    assert convs[0]["id"] != seeded["conversation_id"]
    msgs = client.get(f"/api/conversations/{convs[0]['id']}/messages").json()
    assert [m["content"] for m in msgs] == ["build a payroll form", "done"]

    arts = client.get(f"/api/projects/{new_pid}/artifacts").json()
    kinds = {a["kind"] for a in arts}
    assert kinds == {"formSpec", "ruleSpec", "package"}
    spec = next(a for a in arts if a["kind"] == "formSpec")
    full = client.get(f"/api/artifacts/{spec['id']}").json()
    assert full["payload"] == FORM_PAYLOAD
    pkg = next(a for a in arts if a["kind"] == "package")
    assert pkg["hasFile"] is True
    dl = client.get(f"/api/artifacts/{pkg['id']}/download")
    assert dl.status_code == 200 and dl.content == b"PK-test-package-bytes"

    deps = client.get(f"/api/projects/{new_pid}/deployments").json()
    assert len(deps) == 1 and deps[0]["conversationId"] == convs[0]["id"]
    assert deps[0]["checksum"] == seeded["package_checksum"]
    rexes = client.get(f"/api/projects/{new_pid}/rule-executions").json()
    assert len(rexes) == 1 and rexes[0]["ruleName"] == "Allocate Payroll"

    ctxs = client.get(f"/api/projects/{new_pid}/contexts").json()
    assert len(ctxs) == 1 and ctxs[0]["application"] == "MCWPCF"
    assert imported["activeContextVersionId"] == ctxs[0]["id"]
    envs = client.get(f"/api/projects/{new_pid}/environments").json()
    assert len(envs) == 1 and envs[0]["name"] == "Dev"
    assert imported["activeEnvironmentId"] == envs[0]["id"]

    # the source project is untouched
    assert client.get(f"/api/projects/{old_pid}").status_code == 200


def _bundle_with(members: dict[str, bytes], manifest_files: list[str] | None = None) -> bytes:
    checksums = {n: sha256(b).hexdigest() for n, b in members.items()}
    manifest = {"format": "epmwizard-project-bundle", "bundleFormatVersion": "1.0.0",
                "appVersion": "0", "exportedAt": "2026-01-01T00:00:00+00:00",
                "files": manifest_files if manifest_files is not None else sorted(members),
                "checksums": checksums}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for n, b in members.items():
            zf.writestr(n, b)
    return buf.getvalue()


def test_import_rejects_non_zip(client):
    r = client.post("/api/projects/import", files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert r.status_code == 400
    assert "zip" in r.json()["detail"].lower()


def test_import_rejects_missing_manifest(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("project.json", "{}")
    r = client.post("/api/projects/import", files={"file": ("x.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400
    assert "manifest" in r.json()["detail"]


def test_import_rejects_traversal_member_names(client):
    r = client.post("/api/projects/import",
                    files={"file": ("x.zip", _bundle_with({"../evil.json": b"{}"}), "application/zip")})
    assert r.status_code == 400
    assert "unexpected bundle member" in r.json()["detail"]


def test_import_rejects_checksum_mismatch(client):
    members = {n: b"[]" for n in
               ("environments.json", "conversations.json", "messages.json", "artifacts.json",
                "context_versions.json", "context_records.json", "deployments.json",
                "rule_executions.json")}
    members["project.json"] = json.dumps({"name": "X"}).encode()
    bundle = _bundle_with(members)
    # corrupt project.json inside the zip while keeping the manifest checksum
    zf_in = zipfile.ZipFile(io.BytesIO(bundle))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf_out:
        for name in zf_in.namelist():
            data = zf_in.read(name)
            zf_out.writestr(name, b'{"name": "tampered"}' if name == "project.json" else data)
    r = client.post("/api/projects/import", files={"file": ("x.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400
    assert "checksum mismatch" in r.json()["detail"]


def test_import_minimal_valid_bundle(client):
    members = {n: b"[]" for n in
               ("environments.json", "conversations.json", "messages.json", "artifacts.json",
                "context_versions.json", "context_records.json", "deployments.json",
                "rule_executions.json")}
    members["project.json"] = json.dumps({"name": "Minimal import"}).encode()
    r = client.post("/api/projects/import",
                    files={"file": ("x.zip", _bundle_with(members), "application/zip")})
    assert r.status_code == 201
    assert r.json()["name"] == "Minimal import"


# --- Backups -----------------------------------------------------------------


def test_backup_endpoints_and_startup_backup(client):
    if not get_settings().is_sqlite:
        # Managed database: no file backups — empty list, 409 on create.
        assert client.get("/api/diagnostics/backups").json() == []
        refused = client.post("/api/diagnostics/backups")
        assert refused.status_code == 409
        assert "managed database" in refused.json()["detail"]
        return

    # the lifespan hook already ran one backup when the client started
    initial = client.get("/api/diagnostics/backups").json()
    assert len(initial) >= 1

    created = client.post("/api/diagnostics/backups")
    assert created.status_code == 201
    body = created.json()
    assert body["filename"].startswith("epmwizard-") and body["filename"].endswith(".db")
    assert body["sizeBytes"] > 0 and body["createdAt"]

    listed = client.get("/api/diagnostics/backups").json()
    assert any(b["filename"] == body["filename"] for b in listed)
    # newest first
    assert [b["filename"] for b in listed] == sorted((b["filename"] for b in listed), reverse=True)


def test_backup_rotation_keeps_n_most_recent():
    if not get_settings().is_sqlite:
        with pytest.raises(backups_svc.ManagedDatabaseError):
            backups_svc.create_backup(keep=2)
        return
    for _ in range(3):
        backups_svc.create_backup(keep=2)
    remaining = backups_svc.list_backups()
    assert len(remaining) == 2


# --- Disk usage --------------------------------------------------------------


def test_disk_usage(client, session):
    seeded = _seed_project(session)
    d = client.get("/api/diagnostics/disk").json()
    assert d["dbBytes"] > 0  # SQLite file size, or pg_database_size on Postgres
    if get_settings().is_sqlite:
        assert d["backupsBytes"] > 0
    else:
        assert d["backupsBytes"] == 0  # managed database: no local backup files
    mine = next(p for p in d["projects"] if p["projectId"] == seeded["project_id"])
    assert mine["name"] == "Bundle Source"
    assert mine["artifactCount"] == 3
    assert mine["artifactBytes"] > len(b"PK-test-package-bytes")


# --- Impact analysis ---------------------------------------------------------


def test_impact_analysis_exact_case_insensitive(client, session):
    seeded = _seed_project(session)
    pid = seeded["project_id"]

    r = client.get(f"/api/projects/{pid}/impact", params={"member": "total payroll"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "total payroll"
    by_type = {ref["artifactType"]: ref for ref in body["references"]}
    assert set(by_type) == {"formSpec", "ruleSpec"}
    assert "rows[0].selection.member" in by_type["formSpec"]["locations"]
    assert "referencedMembers[0]" in by_type["ruleSpec"]["locations"]
    assert by_type["formSpec"]["artifactName"] == "Payroll Review"

    # identifier-first: substrings never match
    none = client.get(f"/api/projects/{pid}/impact", params={"member": "Payroll"}).json()
    assert none["references"] == []

    # dimension names are found too
    dim = client.get(f"/api/projects/{pid}/impact", params={"member": "Account"}).json()
    assert any("rows[0].dimension" in ref["locations"] for ref in dim["references"])


def test_impact_analysis_errors(client, session):
    seeded = _seed_project(session)
    assert client.get(f"/api/projects/{seeded['project_id']}/impact",
                      params={"member": "   "}).status_code == 400
    assert client.get("/api/projects/nope/impact", params={"member": "X"}).status_code == 404


# --- EPM Automate script export ----------------------------------------------


def test_deployment_script_sh(client, session):
    seeded = _seed_project(session)
    did = seeded["deployment_id"]
    r = client.get(f"/api/deployments/{did}/script", params={"format": "sh"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    script = r.text
    assert f"# Deployment: {did}" in script
    assert f"sha256): {seeded['package_checksum']}" in script
    assert "set -euo pipefail" in script
    assert 'epmautomate login "$EPM_USER" "$EPM_PASSWORD_FILE" "$EPM_URL"' in script
    assert f'epmautomate uploadfile "{seeded["package_filename"]}"' in script
    assert "epmautomate importsnapshot" in script
    assert "epmautomate logout" in script
    # placeholders only — no credential values anywhere
    assert "password=" not in script.lower()
    # deterministic: identical bytes on every call
    assert client.get(f"/api/deployments/{did}/script", params={"format": "sh"}).text == script


def test_deployment_script_ps1_and_errors(client, session):
    seeded = _seed_project(session)
    did = seeded["deployment_id"]
    r = client.get(f"/api/deployments/{did}/script", params={"format": "ps1"})
    assert r.status_code == 200
    assert '$ErrorActionPreference = "Stop"' in r.text
    assert "epmautomate login $env:EPM_USER $env:EPM_PASSWORD_FILE $env:EPM_URL" in r.text
    assert "finally {" in r.text and "epmautomate logout" in r.text

    assert client.get(f"/api/deployments/{did}/script", params={"format": "exe"}).status_code == 400
    assert client.get("/api/deployments/missing/script", params={"format": "sh"}).status_code == 404
