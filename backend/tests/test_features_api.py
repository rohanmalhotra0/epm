"""API tests for conversation management, global search, the skill catalog and
the diagnostics log buffer."""

from __future__ import annotations

from app.db.models import Artifact, Message
from app.logging import get_logger
from app.security.redaction import REDACTION
from app.services import conversations as conversations_svc


def _pid(client) -> str:
    return client.get("/api/projects").json()[0]["id"]


# --- Conversation management -------------------------------------------------


def test_conversation_patch_pin_archive_and_ordering(client):
    pid = _pid(client)
    a = client.post(f"/api/projects/{pid}/conversations", json={"title": "Alpha convo"}).json()
    b = client.post(f"/api/projects/{pid}/conversations", json={"title": "Beta convo"}).json()
    assert a["pinned"] is False and a["archived"] is False

    # rename + pin the older conversation
    r = client.patch(f"/api/conversations/{a['id']}", json={"title": "Alpha renamed", "pinned": True})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Alpha renamed"
    assert body["pinned"] is True and body["archived"] is False

    # pinned conversations sort first even though b is more recent
    convs = client.get(f"/api/projects/{pid}/conversations").json()
    ids = [c["id"] for c in convs]
    assert ids.index(a["id"]) < ids.index(b["id"])
    assert all("pinned" in c and "archived" in c for c in convs)

    # archived conversations drop out of the default list
    assert client.patch(f"/api/conversations/{b['id']}", json={"archived": True}).json()["archived"] is True
    ids = [c["id"] for c in client.get(f"/api/projects/{pid}/conversations").json()]
    assert b["id"] not in ids
    ids_all = [c["id"] for c in client.get(
        f"/api/projects/{pid}/conversations", params={"include_archived": True}).json()]
    assert b["id"] in ids_all

    # False is applied, not treated as "unset"
    assert client.patch(f"/api/conversations/{a['id']}", json={"pinned": False}).json()["pinned"] is False


def test_conversation_patch_unknown_404(client):
    assert client.patch("/api/conversations/does-not-exist", json={"title": "x"}).status_code == 404


def test_conversation_delete_cascades_messages(client, session):
    pid = _pid(client)
    cid = client.post(f"/api/projects/{pid}/conversations", json={"title": "Doomed"}).json()["id"]
    conversations_svc.add_message(session, cid, role="user", content="hello cascade")
    session.commit()
    assert session.query(Message).filter_by(conversation_id=cid).count() == 1

    assert client.delete(f"/api/conversations/{cid}").status_code == 204
    assert session.query(Message).filter_by(conversation_id=cid).count() == 0
    assert client.get(f"/api/conversations/{cid}/messages").status_code == 404


# --- Global search -----------------------------------------------------------


def test_global_search_across_sources(client, session):
    pid = _pid(client)
    cid = client.post(f"/api/projects/{pid}/conversations", json={"title": "Payroll planning"}).json()["id"]
    conversations_svc.add_message(
        session, cid, role="user", content="How do I allocate payroll overhead across entities?")
    session.add(Artifact(project_id=pid, kind="xml", name="Payroll Form",
                         content="<form>total payroll allocation</form>"))
    session.commit()

    res = client.get(f"/api/projects/{pid}/search", params={"q": "payroll"}).json()
    results = res["results"]
    assert {"conversation", "message", "artifact"} <= {r["type"] for r in results}

    msg_hit = next(r for r in results if r["type"] == "message")
    assert msg_hit["conversationId"] == cid
    assert "payroll" in msg_hit["snippet"].lower()
    assert msg_hit["title"] == "Payroll planning"

    art_hit = next(r for r in results if r["type"] == "artifact")
    assert art_hit["title"] == "Payroll Form"

    # camelCase field names throughout
    assert all("updatedAt" in r and "conversationId" in r for r in results)


def test_global_search_limit_escaping_and_404(client):
    pid = _pid(client)
    # LIKE wildcards are matched literally, not as wildcards
    res = client.get(f"/api/projects/{pid}/search", params={"q": "zzz%never_matches%"}).json()
    assert res["results"] == []
    # blank query returns nothing
    assert client.get(f"/api/projects/{pid}/search", params={"q": "   "}).json()["results"] == []
    # limit is respected
    res = client.get(f"/api/projects/{pid}/search", params={"q": "a", "limit": 1}).json()
    assert len(res["results"]) <= 1
    # unknown project
    assert client.get("/api/projects/does-not-exist/search", params={"q": "x"}).status_code == 404


# --- Skill catalog -----------------------------------------------------------


def test_meta_skills_catalog(client):
    skills = client.get("/api/meta/skills").json()["skills"]
    names = {s["name"] for s in skills}
    assert {"forms", "reports", "rules", "epmAutomate", "help", "chat"} <= names
    for s in skills:
        assert set(s) == {"name", "title", "description", "examples"}
        assert s["title"] and s["description"]
        assert isinstance(s["examples"], list)
    forms = next(s for s in skills if s["name"] == "forms")
    assert forms["title"] == "Form Builder"
    assert any("form" in ex.lower() for ex in forms["examples"])
    # chat declares no intent examples; the catalog supplies fallbacks
    chat = next(s for s in skills if s["name"] == "chat")
    assert chat["examples"]


# --- Diagnostics log buffer ---------------------------------------------------


def test_diagnostics_logs_buffer_and_redaction(client):
    log = get_logger("test.diagnostics")
    log.info("diag_buffer_probe_one", detail="hello")
    log.info("diag_buffer_probe_two", password="supersecretvalue",
             creds={"api_key": "sk-not-a-real-key"})

    logs = client.get("/api/diagnostics/logs", params={"limit": 50}).json()["logs"]
    assert logs

    two = next(e for e in logs if e["event"] == "diag_buffer_probe_two")
    one = next(e for e in logs if e["event"] == "diag_buffer_probe_one")
    # newest first
    assert logs.index(two) < logs.index(one)

    assert one["logger"] == "test.diagnostics"
    assert one["level"] == "info"
    assert one["ts"]
    assert one["data"]["detail"] == "hello"

    # secrets never surface through the API
    assert two["data"]["password"] == REDACTION
    assert two["data"]["creds"]["api_key"] == REDACTION


def test_diagnostics_logs_limit(client):
    log = get_logger("test.diagnostics")
    for i in range(5):
        log.info("diag_limit_probe", i=i)
    logs = client.get("/api/diagnostics/logs", params={"limit": 3}).json()["logs"]
    assert len(logs) == 3
