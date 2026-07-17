"""HTTP API + SSE streaming tests via TestClient (spec sections 7, 8, 9, 41)."""

from __future__ import annotations

import re


def _events(sse_text: str) -> list[str]:
    return re.findall(r"event: (\w+)", sse_text)


def _blocks(sse_text: str) -> list[str]:
    return re.findall(r'"type": ?"(\w+)"', sse_text)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_projects_and_defaults(client):
    projects = client.get("/api/projects").json()
    assert any(p["isDefault"] for p in projects)
    pid = projects[0]["id"]
    envs = client.get(f"/api/projects/{pid}/environments").json()
    assert any(e["demo"] for e in envs)
    providers = client.get("/api/providers").json()
    assert any(p["providerType"] == "mock" for p in providers)


def test_diagnostics_healthy(client):
    d = client.get("/api/diagnostics").json()
    assert d["redactionHealthy"] is True
    names = {s["name"]: s["status"] for s in d["subsystems"]}
    assert names["SQLite database"] == "ok"
    assert names["Redaction"] == "ok"


def test_skills_and_tools_catalog(client):
    skills = {s["name"] for s in client.get("/api/skills").json()["skills"]}
    assert "/forms" in skills and "/architecture" in skills
    tools = client.get("/api/tools").json()["tools"]
    assert any(t["name"] == "run_business_rule" and t["requiresApproval"] for t in tools)


def test_context_build(client):
    pid = client.get("/api/projects").json()[0]["id"]
    cv = client.post(f"/api/projects/{pid}/contexts/build?mode=deep").json()
    assert cv["counts"]["members"] == 80
    # member search via active context
    res = client.get(f"/api/projects/{pid}/context/search", params={"q": "payroll", "dimension": "Account"}).json()
    assert any(m["member"] == "Total Payroll" for m in res["matches"])


def test_streaming_form_deploy_over_http(client):
    pid = client.get("/api/projects").json()[0]["id"]
    client.post(f"/api/projects/{pid}/contexts/build?mode=deep")
    cid = client.post(f"/api/projects/{pid}/conversations", json={}).json()["id"]

    def send(text):
        return client.post(f"/api/conversations/{cid}/messages", json={"content": text}).text

    create = send("Create an Actuals form with level-zero descendants of Total Payroll in rows")
    assert "done" in _events(create)
    assert "formPreview" in _blocks(create)

    assert "deploymentPlan" in send("deploy")
    assert "deploymentResult" in send("confirm deploy")

    msgs = client.get(f"/api/conversations/{cid}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user", "assistant"]

    deps = client.get(f"/api/projects/{pid}/deployments").json()
    assert deps[0]["success"] and deps[0]["verified"]

    kinds = {a["kind"] for a in client.get(f"/api/projects/{pid}/artifacts").json()}
    assert {"formSpec", "xml", "package"} <= kinds


def test_secret_in_message_is_redacted_and_warned(client):
    pid = client.get("/api/projects").json()[0]["id"]
    cid = client.post(f"/api/projects/{pid}/conversations", json={}).json()["id"]
    resp = client.post(f"/api/conversations/{cid}/messages",
                       json={"content": "my password=SuperSecret123 please connect"}).text
    assert "SuperSecret123" not in resp
    msgs = client.get(f"/api/conversations/{cid}/messages").json()
    assert "SuperSecret123" not in msgs[0]["content"]
