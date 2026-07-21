"""Authorization / owner-scoping enumeration test (multi-user security).

The security guarantee: with EPMW_MULTI_USER=true every by-ID and
project-scoped route must return 404 for a non-owning identity, and behave
normally for the owner. This test seeds a full project graph (conversation,
message, context, artifact, attachment, deployment, rule-execution) owned by
``a@x.com`` and then enumerates EVERY guarded route in
routes_conversations.py, routes_artifacts.py, routes_attachments.py (plus the
routes_context.py reference routes) for both the owner (``a@x.com``) and an
attacker (``b@x.com``).

It also asserts the regression path: with multi-user OFF (the default) no
identity header is needed and cross-identity access is unrestricted, i.e. the
guards are true no-ops.
"""

from __future__ import annotations

import contextlib
from hashlib import sha256

from fastapi.testclient import TestClient

import app.config
from app.config import get_settings
from app.db.base import get_sessionmaker
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

A = "a@x.com"
B = "b@x.com"
HEADER = "X-Forwarded-Email"

FORM_PAYLOAD = {
    "schemaVersion": "1.0.0",
    "name": "Payroll Review",
    "application": "MCWPCF",
    "cube": "Plan1",
    "rows": [{"dimension": "Account",
              "selection": {"type": "levelZeroDescendants", "member": "Total Payroll"}}],
    "columns": [{"dimension": "Period", "selection": {"type": "children", "member": "YearTotal"}}],
}


@contextlib.contextmanager
def _multi_user(monkeypatch, enabled: bool):
    """Toggle EPMW_MULTI_USER and reset the lru_cached settings around the block."""
    monkeypatch.setenv("EPMW_MULTI_USER", "true" if enabled else "false")
    app.config.get_settings.cache_clear()
    try:
        yield
    finally:
        monkeypatch.delenv("EPMW_MULTI_USER", raising=False)
        app.config.get_settings.cache_clear()


def _seed(owner_id: str | None) -> dict:
    """Insert a full project graph owned by ``owner_id`` directly (bypassing the
    service so the owner is controlled explicitly). Returns all resource ids."""
    settings = get_settings()
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        project = Project(name="Authz Source", description=None, is_default=False, owner_id=owner_id)
        s.add(project)
        s.flush()

        env = EnvironmentProfile(project_id=project.id, name="Dev", base_url="https://example.test",
                                 username="planner", classification="development", demo=True)
        s.add(env)
        s.flush()
        project.active_environment_id = env.id

        conv = Conversation(project_id=project.id, title="Payroll chat")
        s.add(conv)
        s.flush()
        user_msg = Message(conversation_id=conv.id, role="user", content="build a payroll form")
        s.add(user_msg)
        s.flush()
        s.add(Message(conversation_id=conv.id, role="assistant", content="done", parent_id=user_msg.id))

        cv = ContextVersion(project_id=project.id, environment_id=env.id, application="MCWPCF",
                            label="Deep context", mode="deep", counts={"members": 1}, active=True)
        s.add(cv)
        s.flush()
        s.add(ContextRecord(context_version_id=cv.id, project_id=project.id, kind="member",
                            name="Total Payroll", dimension="Account", search_text="total payroll"))
        cv2 = ContextVersion(project_id=project.id, environment_id=env.id, application="MCWPCF",
                             label="Second context", mode="deep", counts={"members": 1}, active=False)
        s.add(cv2)
        s.flush()
        s.add(ContextRecord(context_version_id=cv2.id, project_id=project.id, kind="member",
                            name="Salaries", dimension="Account", search_text="salaries"))
        project.active_context_version_id = cv.id

        spec_art = Artifact(project_id=project.id, kind="formSpec", name="Payroll Review",
                            payload=FORM_PAYLOAD, context_version=cv.id)
        s.add(spec_art)
        deletable_art = Artifact(project_id=project.id, kind="formSpec", name="Deletable",
                                 payload={"k": "v"})
        s.add(deletable_art)

        pkg_bytes = b"PK-test-package-bytes"
        checksum = sha256(pkg_bytes).hexdigest()
        pkg_path = settings.artifacts_dir / f"Authz_{checksum[:12]}.zip"
        pkg_path.write_bytes(pkg_bytes)
        pkg_art = Artifact(project_id=project.id, kind="package", name="Payroll Review.zip",
                           path=str(pkg_path), checksum=checksum)
        s.add(pkg_art)
        s.flush()

        dep = Deployment(project_id=project.id, conversation_id=conv.id, environment_name="Dev",
                         classification="development", application="MCWPCF",
                         artifact_name="Payroll Review", artifact_type="planningForm",
                         operation="create", operation_class="modifying", approved=True,
                         checksum=checksum, success=True, verified=True, demo_mode=True)
        s.add(dep)
        rex = RuleExecution(project_id=project.id, conversation_id=conv.id,
                            rule_name="Allocate Payroll", application="MCWPCF", cube="Plan1",
                            status="completed", prompt_values={"Scenario": "Actual"})
        s.add(rex)
        s.flush()
        s.commit()
        return {
            "project_id": project.id, "conversation_id": conv.id, "user_message_id": user_msg.id,
            "cv_id": cv.id, "cv2_id": cv2.id, "spec_artifact_id": spec_art.id,
            "deletable_artifact_id": deletable_art.id, "package_artifact_id": pkg_art.id,
            "deployment_id": dep.id, "rule_execution_id": rex.id,
        }
    finally:
        s.close()


def _upload_csv(client, conversation_id: str, headers: dict) -> object:
    return client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": ("data.csv", b"Account,Amount\nSalaries,100\n", "text/csv")},
        headers=headers,
    )


def test_authz_multi_user_on_enumerates_every_route(monkeypatch):
    """With multi-user ON: owner A gets 200/expected, attacker B gets 404, on
    every guarded route across the four route modules."""
    from app.main import app

    ids = _seed(owner_id=A)
    pid = ids["project_id"]
    cid = ids["conversation_id"]

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        ha = {HEADER: A}
        hb = {HEADER: B}

        # Owner A uploads an attachment (exercises the upload route positively).
        up = _upload_csv(client, cid, ha)
        assert up.status_code == 201, up.text
        attachment_id = up.json()["id"]

        # ---- project-scoped routes (path has {project_id}) ------------------
        project_scoped = [
            ("GET", f"/api/projects/{pid}/conversations", None),
            ("GET", f"/api/projects/{pid}/artifacts", None),
            ("GET", f"/api/projects/{pid}/deployments", None),
            ("GET", f"/api/projects/{pid}/rule-executions", None),
            ("GET", f"/api/projects/{pid}/contexts", None),
            ("GET", f"/api/projects/{pid}/context/search?q=payroll", None),
        ]
        for method, url, _ in project_scoped:
            assert client.request(method, url, headers=ha).status_code == 200, url
            assert client.request(method, url, headers=hb).status_code == 404, url

        # create conversation (project-scoped POST)
        assert client.post(f"/api/projects/{pid}/conversations", json={}, headers=hb).status_code == 404
        created = client.post(f"/api/projects/{pid}/conversations", json={}, headers=ha)
        assert created.status_code == 201
        throwaway_conv = created.json()["id"]

        # ---- by-ID conversation routes --------------------------------------
        assert client.get(f"/api/conversations/{cid}/messages", headers=hb).status_code == 404
        assert client.get(f"/api/conversations/{cid}/messages", headers=ha).status_code == 200

        assert client.patch(f"/api/conversations/{cid}", json={"title": "hax"},
                            headers=hb).status_code == 404
        assert client.patch(f"/api/conversations/{cid}", json={"title": "mine"},
                            headers=ha).status_code == 200

        # streaming send-message: attacker blocked BEFORE any streaming
        assert client.post(f"/api/conversations/{cid}/messages", json={"content": "hi"},
                           headers=hb).status_code == 404
        assert client.post(f"/api/conversations/{cid}/messages", json={"content": "hello"},
                           headers=ha).status_code == 200

        # streaming branch: attacker blocked BEFORE any streaming
        mid = ids["user_message_id"]
        assert client.post(f"/api/conversations/{cid}/messages/{mid}/branch",
                           json={"content": "edit"}, headers=hb).status_code == 404
        assert client.post(f"/api/conversations/{cid}/messages/{mid}/branch",
                           json={"content": "edited"}, headers=ha).status_code == 200

        # delete conversation: attacker blocked on A's conv; owner deletes throwaway
        assert client.delete(f"/api/conversations/{cid}", headers=hb).status_code == 404
        assert client.delete(f"/api/conversations/{throwaway_conv}", headers=ha).status_code == 204

        # ---- by-ID artifact routes ------------------------------------------
        aid = ids["spec_artifact_id"]
        pkg_id = ids["package_artifact_id"]
        assert client.get(f"/api/artifacts/{aid}", headers=hb).status_code == 404
        assert client.get(f"/api/artifacts/{aid}", headers=ha).status_code == 200
        assert client.get(f"/api/artifacts/{pkg_id}/download", headers=hb).status_code == 404
        assert client.get(f"/api/artifacts/{pkg_id}/download", headers=ha).status_code == 200
        # delete artifact: attacker blocked on A's artifact; owner deletes the deletable one
        assert client.delete(f"/api/artifacts/{aid}", headers=hb).status_code == 404
        assert client.delete(f"/api/artifacts/{ids['deletable_artifact_id']}",
                             headers=ha).status_code == 204

        # ---- by-ID deployment routes ----------------------------------------
        did = ids["deployment_id"]
        assert client.get(f"/api/deployments/{did}", headers=hb).status_code == 404
        assert client.get(f"/api/deployments/{did}", headers=ha).status_code == 200
        assert client.get(f"/api/deployments/{did}/script", headers=hb).status_code == 404
        assert client.get(f"/api/deployments/{did}/script", headers=ha).status_code == 200

        # ---- by-ID attachment routes ----------------------------------------
        assert client.get(f"/api/attachments/{attachment_id}", headers=hb).status_code == 404
        assert client.get(f"/api/attachments/{attachment_id}", headers=ha).status_code == 200
        assert client.get(f"/api/attachments/{attachment_id}/analysis",
                          headers=hb).status_code == 404
        assert client.get(f"/api/attachments/{attachment_id}/analysis",
                          headers=ha).status_code == 200
        # upload into A's conversation as B is blocked before file processing
        assert _upload_csv(client, cid, hb).status_code == 404

        # ---- by-ID context routes (routes_context.py reference) -------------
        cv_id = ids["cv_id"]
        cv2_id = ids["cv2_id"]
        assert client.post(f"/api/contexts/{cv_id}/activate", headers=hb).status_code == 404
        assert client.post(f"/api/contexts/{cv_id}/activate", headers=ha).status_code == 200
        assert client.get(f"/api/contexts/{cv_id}/diff?against={cv2_id}",
                          headers=hb).status_code == 404
        assert client.get(f"/api/contexts/{cv_id}/diff?against={cv2_id}",
                          headers=ha).status_code == 200
        assert client.get(f"/api/contexts/{cv_id}/export.md", headers=hb).status_code == 404
        assert client.get(f"/api/contexts/{cv_id}/export.md", headers=ha).status_code == 200
        # delete context: attacker blocked on active cv; owner deletes the second cv
        assert client.delete(f"/api/contexts/{cv_id}", headers=hb).status_code == 404
        assert client.delete(f"/api/contexts/{cv2_id}", headers=ha).status_code == 204


def test_authz_multi_user_off_no_scoping_regression(monkeypatch):
    """With multi-user OFF (default): no identity header is needed and any
    identity may access any resource — the guards are true no-ops."""
    from app.main import app

    ids = _seed(owner_id=None)  # legacy-style project, no owner
    pid = ids["project_id"]
    cid = ids["conversation_id"]
    aid = ids["spec_artifact_id"]
    did = ids["deployment_id"]

    with _multi_user(monkeypatch, False), TestClient(app) as client:
        # No header at all -> everything works.
        assert client.get(f"/api/projects/{pid}/conversations").status_code == 200
        assert client.get(f"/api/projects/{pid}/artifacts").status_code == 200
        assert client.get(f"/api/projects/{pid}/deployments").status_code == 200
        assert client.get(f"/api/projects/{pid}/rule-executions").status_code == 200
        assert client.get(f"/api/projects/{pid}/contexts").status_code == 200
        assert client.get(f"/api/conversations/{cid}/messages").status_code == 200
        assert client.get(f"/api/artifacts/{aid}").status_code == 200
        assert client.get(f"/api/deployments/{did}").status_code == 200

        # A stray identity header is ignored (no scoping when OFF).
        stranger = {HEADER: B}
        assert client.get(f"/api/projects/{pid}/conversations", headers=stranger).status_code == 200
        assert client.get(f"/api/conversations/{cid}/messages", headers=stranger).status_code == 200
        assert client.get(f"/api/artifacts/{aid}", headers=stranger).status_code == 200
        assert client.get(f"/api/deployments/{did}", headers=stranger).status_code == 200

        # An upload with a stray header still succeeds.
        assert _upload_csv(client, cid, stranger).status_code == 201
