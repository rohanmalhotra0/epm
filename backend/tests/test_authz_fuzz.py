"""Adversarial authorization / owner-scoping fuzzing (multi-user security).

This goes *further* than tests/test_authz.py: it hammers the identity header
parsing (spoofing, case, whitespace, unicode/homoglyph, length, injection,
duplicates) and it targets **confused-deputy** paths where a route authorizes
one resource (a conversation / project the attacker owns) but then resolves a
*second* resource purely by id (a message, a context version, an attachment)
belonging to a different owner.

Three confused-deputy holes were found and fixed while writing this test:

1. ``POST /api/projects/{B}/active-context/{A_ctx}`` — an owner authorized for
   their own project could point its active context at another owner's context
   version (resolved by id only) and read it back through their own turns.
   Fixed in routes_projects.set_active_context (project-membership check).
2. ``POST /api/conversations/{B_conv}/messages/{A_msg}/branch`` — branch
   resolved the message by id and mutated *its* conversation's history, so an
   owner could deactivate/inject into another owner's conversation. Fixed in
   routes_conversations.branch_message (message-belongs-to-conversation check).
3. ``POST /api/conversations/{B_conv}/messages`` with ``attachments=[A_att]``
   — the user-message persister linked any attachment id and fed it to the
   turn, exfiltrating another owner's parsed file. Fixed in
   routes_conversations._persist_user_message (project-membership check).

Also asserts the flag-OFF regression (headers ignored, no scoping) and CREATE
ownership (owner_id set to the caller; another owner can't see it).
"""

from __future__ import annotations

import contextlib
import uuid
from hashlib import sha256

from fastapi.testclient import TestClient

import app.config
from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import (
    Attachment,
    ContextRecord,
    ContextVersion,
    Conversation,
    EnvironmentProfile,
    Message,
    Project,
)

HEADER = "X-Forwarded-Email"


def _u(prefix: str) -> str:
    """A unique owner email per test run (the DB is shared across the session)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@x.com"


@contextlib.contextmanager
def _multi_user(monkeypatch, enabled: bool):
    monkeypatch.setenv("EPMW_MULTI_USER", "true" if enabled else "false")
    app.config.get_settings.cache_clear()
    try:
        yield
    finally:
        monkeypatch.delenv("EPMW_MULTI_USER", raising=False)
        app.config.get_settings.cache_clear()


def _seed(owner_id: str | None) -> dict:
    """Insert a minimal but complete graph (project, env, conversation, a user
    message, two context versions, one attachment) owned by ``owner_id``."""
    settings = get_settings()
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        project = Project(name="Fuzz Source", description=None, is_default=False, owner_id=owner_id)
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

        cv = ContextVersion(project_id=project.id, environment_id=env.id, application="MCWPCF",
                            label="Deep", mode="deep", counts={"members": 1}, active=True)
        s.add(cv)
        s.flush()
        s.add(ContextRecord(context_version_id=cv.id, project_id=project.id, kind="member",
                            name="Total Payroll", dimension="Account", search_text="total payroll"))
        cv2 = ContextVersion(project_id=project.id, environment_id=env.id, application="MCWPCF",
                             label="Second", mode="deep", counts={"members": 1}, active=False)
        s.add(cv2)
        s.flush()
        s.add(ContextRecord(context_version_id=cv2.id, project_id=project.id, kind="member",
                            name="Salaries", dimension="Account", search_text="salaries"))
        project.active_context_version_id = cv.id

        # A directly-seeded attachment owned by this project.
        att_dir = settings.data_dir / "attachments" / f"seed-{uuid.uuid4().hex[:8]}"
        att_dir.mkdir(parents=True, exist_ok=True)
        att_path = att_dir / "secret.csv"
        att_path.write_bytes(b"Account,Amount\nSalaries,999999\n")
        att = Attachment(project_id=project.id, conversation_id=conv.id, filename="secret.csv",
                         media_type="text/csv", size_bytes=att_path.stat().st_size,
                         path=str(att_path), checksum=sha256(att_path.read_bytes()).hexdigest(),
                         text_extract="secret.csv")
        s.add(att)
        s.flush()
        s.commit()
        return {
            "owner": owner_id, "project_id": project.id, "conversation_id": conv.id,
            "user_message_id": user_msg.id, "cv_id": cv.id, "cv2_id": cv2.id,
            "attachment_id": att.id, "env_id": env.id,
        }
    finally:
        s.close()


def _get_attachment_message_id(attachment_id: str) -> str | None:
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        att = s.get(Attachment, attachment_id)
        return att.message_id if att else "MISSING"
    finally:
        s.close()


def _active_message_count(conversation_id: str) -> int:
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        return (
            s.query(Message)
            .filter_by(conversation_id=conversation_id, active=True)
            .count()
        )
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Header parsing / spoofing                                                    #
# --------------------------------------------------------------------------- #

def test_header_case_insensitive_and_missing(monkeypatch):
    """FastAPI headers are case-insensitive; missing/empty -> "local"."""
    from starlette.requests import Request

    from app.api.deps import get_current_owner

    def _req(header_pairs: list[tuple[str, str]]) -> Request:
        scope = {"type": "http",
                 "headers": [(k.lower().encode(), v.encode()) for k, v in header_pairs]}
        return Request(scope)

    with _multi_user(monkeypatch, True):
        # Different case of the header NAME still resolves the identity.
        assert get_current_owner(_req([("X-FORWARDED-EMAIL", "a@x.com")])) == "a@x.com"
        assert get_current_owner(_req([("x-forwarded-email", "a@x.com")])) == "a@x.com"
        # Missing header and empty value both fall back to "local".
        assert get_current_owner(_req([])) == "local"
        assert get_current_owner(_req([(HEADER, "")])) == "local"
        # Duplicate headers: the FIRST value wins deterministically — an attacker
        # appending a second header cannot override the proxy-set first one.
        assert get_current_owner(_req([(HEADER, "a@x.com"), (HEADER, "b@x.com")])) == "a@x.com"


def test_header_spoof_variants_cannot_reach_other_owner(monkeypatch):
    """Whitespace / unicode-homoglyph / very-long / empty header values resolve
    to a *different* owner string and therefore cannot reach A's project."""
    from app.main import app

    # Guarantee an ASCII 'a' in the email so the homoglyph swap below is a real
    # (distinct) mutation rather than a no-op.
    owner_a = f"alice-{uuid.uuid4().hex[:8]}@x.com"
    ids = _seed(owner_id=owner_a)
    pid = ids["project_id"]

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        assert client.get(f"/api/projects/{pid}", headers={HEADER: owner_a}).status_code == 200

        spoofs = [
            " " + owner_a,           # leading whitespace (no trimming)
            owner_a + " ",           # trailing whitespace
            owner_a.upper(),         # case-different email value (not normalised)
            owner_a.replace("a", "а", 1),  # Cyrillic homoglyph 'а'
            "x" * 10000,             # very long
            "",                      # empty -> "local"
        ]
        for spoof in spoofs:
            try:
                r = client.get(f"/api/projects/{pid}", headers={HEADER: spoof})
            except Exception:
                continue  # transport rejected the value outright — also non-access
            assert r.status_code == 404, f"spoof {spoof!r} reached A's project"

        # No header at all -> "local", still cannot reach A.
        assert client.get(f"/api/projects/{pid}").status_code == 404


def test_header_injection_newline_cannot_bypass(monkeypatch):
    """A CR/LF-injected header value must not grant access: either the transport
    rejects it outright, or it is treated as one (distinct, non-matching) owner
    string — never as a smuggled second header that authorizes anything."""
    from app.main import app

    victim = f"alice-{uuid.uuid4().hex[:8]}@x.com"
    ids = _seed(owner_id=victim)
    pid = ids["project_id"]

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        try:
            r = client.get(f"/api/projects/{pid}",
                           headers={HEADER: victim + "\r\nX-Injected: 1"})
        except Exception:
            return  # transport rejected the CRLF injection — good
        assert r.status_code == 404, "CRLF-injected header must not authorize"


# --------------------------------------------------------------------------- #
# Confused-deputy: cross-owner second-resource references                      #
# --------------------------------------------------------------------------- #

def test_confused_deputy_activate_foreign_context(monkeypatch):
    """B (owning project B) must not set B's active context to A's context id."""
    from app.main import app

    a = _seed(owner_id=_u("a"))
    b = _seed(owner_id=_u("b"))
    hb = {HEADER: b["owner"]}

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        # B points B's project at A's context version -> 404 (blocked).
        r = client.post(
            f"/api/projects/{b['project_id']}/active-context/{a['cv_id']}", headers=hb)
        assert r.status_code == 404, r.text

        # B's project active context is unchanged (still B's own cv).
        assert client.get(
            f"/api/projects/{b['project_id']}", headers=hb
        ).json()["activeContextVersionId"] == b["cv_id"]

        # Sanity: B CAN activate B's own second context.
        assert client.post(
            f"/api/projects/{b['project_id']}/active-context/{b['cv2_id']}",
            headers=hb).status_code == 200


def test_confused_deputy_branch_foreign_message(monkeypatch):
    """B (owning conv B) must not branch a message id that belongs to A's conv;
    A's conversation history must be untouched."""
    from app.main import app

    a = _seed(owner_id=_u("a"))
    b = _seed(owner_id=_u("b"))
    hb = {HEADER: b["owner"]}
    before = _active_message_count(a["conversation_id"])

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        r = client.post(
            f"/api/conversations/{b['conversation_id']}/messages/{a['user_message_id']}/branch",
            json={"content": "hijack"}, headers=hb)
        assert r.status_code == 404, r.text

    # A's conversation was not mutated (nothing deactivated, nothing injected).
    assert _active_message_count(a["conversation_id"]) == before


def test_confused_deputy_reference_foreign_attachment(monkeypatch):
    """B sending a message in B's conversation must not be able to pull A's
    attachment into the turn: A's attachment stays unlinked."""
    from app.main import app

    a = _seed(owner_id=_u("a"))
    b = _seed(owner_id=_u("b"))
    hb = {HEADER: b["owner"]}

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        # B references A's attachment id while messaging B's own conversation.
        r = client.post(
            f"/api/conversations/{b['conversation_id']}/messages",
            json={"content": "use this", "attachments": [a["attachment_id"]]},
            headers=hb)
        # Streaming endpoint: authorized for B's conv, so 200 — but the foreign
        # attachment must NOT have been linked.
        assert r.status_code == 200, r.text
        r.read()  # drain the SSE body

    # A's attachment was never linked to any of B's messages.
    assert _get_attachment_message_id(a["attachment_id"]) is None


def test_confused_deputy_diff_cross_project_no_leak(monkeypatch):
    """Diffing across owners never returns a 200 diff body (either 400 for the
    cross-project mismatch or 404 for the unauthorized primary)."""
    from app.main import app

    a = _seed(owner_id=_u("a"))
    b = _seed(owner_id=_u("b"))
    hb = {HEADER: b["owner"]}

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        # primary = B's ctx (owned), against = A's ctx -> different project -> 400
        assert client.get(
            f"/api/contexts/{b['cv_id']}/diff?against={a['cv_id']}", headers=hb
        ).status_code != 200
        # primary = A's ctx (not owned) -> must not be 200 either
        assert client.get(
            f"/api/contexts/{a['cv_id']}/diff?against={b['cv_id']}", headers=hb
        ).status_code != 200


def test_own_attachment_reference_links_positively(monkeypatch):
    """Regression: an owner referencing their OWN attachment still links it."""
    from app.main import app

    b = _seed(owner_id=_u("b"))
    hb = {HEADER: b["owner"]}

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        r = client.post(
            f"/api/conversations/{b['conversation_id']}/messages",
            json={"content": "use mine", "attachments": [b["attachment_id"]]},
            headers=hb)
        assert r.status_code == 200
        r.read()

    assert _get_attachment_message_id(b["attachment_id"]) not in (None, "MISSING")


# --------------------------------------------------------------------------- #
# Legacy NULL-owner + CREATE ownership + flag-off regression                   #
# --------------------------------------------------------------------------- #

def test_legacy_null_owner_visible_to_all_and_not_claimed(monkeypatch):
    """Legacy NULL-owner projects are visible to every identity, and no route
    reassigns owner_id — so a malicious owner cannot claim one to hide it from
    others (it stays NULL/shared after any read)."""
    from app.main import app

    legacy = _seed(owner_id=None)
    pid = legacy["project_id"]

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        for who in (_u("x"), _u("y")):
            assert client.get(f"/api/projects/{pid}", headers={HEADER: who}).status_code == 200
            # Interacting (listing) does not silently claim the project.
            assert pid in {p["id"] for p in client.get("/api/projects", headers={HEADER: who}).json()}

    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        assert s.get(Project, pid).owner_id is None  # still shared, never hijacked
    finally:
        s.close()


def test_create_sets_owner_and_hides_from_others(monkeypatch):
    """Creating a project stamps owner_id = caller; a different owner can't see
    it by list or by id."""
    from app.main import app

    a, b = _u("creator"), _u("other")
    with _multi_user(monkeypatch, True), TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "A owned"},
                          headers={HEADER: a}).json()["id"]
        # Persisted owner is A.
        SessionLocal = get_sessionmaker()
        s = SessionLocal()
        try:
            assert s.get(Project, pid).owner_id == a
        finally:
            s.close()
        # B cannot see it in the list nor fetch it by id.
        assert pid not in {p["id"] for p in client.get("/api/projects", headers={HEADER: b}).json()}
        assert client.get(f"/api/projects/{pid}", headers={HEADER: b}).status_code == 404


def test_flag_off_ignores_headers_everywhere(monkeypatch):
    """With multi-user OFF the confused-deputy guards are true no-ops for a
    single owner: a stray identity header changes nothing."""
    from app.main import app

    a = _seed(owner_id=None)
    stranger = {HEADER: _u("stranger")}

    with _multi_user(monkeypatch, False), TestClient(app) as client:
        assert client.get(f"/api/projects/{a['project_id']}", headers=stranger).status_code == 200
        assert client.get(
            f"/api/conversations/{a['conversation_id']}/messages", headers=stranger
        ).status_code == 200
        # Activating own context and branching own message work regardless of header.
        assert client.post(
            f"/api/projects/{a['project_id']}/active-context/{a['cv2_id']}",
            headers=stranger).status_code == 200
        r = client.post(
            f"/api/conversations/{a['conversation_id']}/messages/{a['user_message_id']}/branch",
            json={"content": "edit"}, headers=stranger)
        assert r.status_code == 200
        r.read()


# --------------------------------------------------------------------------- #
# Environment by-id confused-deputy (no path project → resolve env, re-check)  #
# --------------------------------------------------------------------------- #


def _insert_env(project_id: str, *, demo: bool = True) -> str:
    """Insert an environment into an existing project and return its id.

    Called *inside* the TestClient context: the app's startup lifespan runs
    ``seed_defaults`` which purges every ``demo=True`` environment, so an env
    seeded before the client is wiped — this seeds after startup so it survives.
    """
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        env = EnvironmentProfile(project_id=project_id, name="Tenant", base_url="https://example.test",
                                 username="planner", classification="development", demo=demo)
        s.add(env)
        s.flush()
        env_id = env.id
        s.commit()
        return env_id
    finally:
        s.close()


def test_confused_deputy_environment_by_id_blocked(monkeypatch):
    """A's Oracle environment id must be untouchable by B on every by-id route
    (connect / test / disconnect / delete). Before the fix these routes resolved
    the environment purely by id with no owner check, so B could enumerate,
    probe, disconnect, or delete A's environment. Each must 404 for B and A's
    environment must still exist afterward."""
    from app.main import app

    a = _seed(owner_id=_u("a"))
    b = _seed(owner_id=_u("b"))
    ha, hb = {HEADER: a["owner"]}, {HEADER: b["owner"]}

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        env = _insert_env(a["project_id"])  # seed after startup so it survives
        assert client.post(f"/api/environments/{env}/connect", json={}, headers=hb).status_code == 404
        assert client.post(f"/api/environments/{env}/test", headers=hb).status_code == 404
        assert client.post(f"/api/environments/{env}/disconnect", headers=hb).status_code == 404
        assert client.delete(f"/api/environments/{env}", headers=hb).status_code == 404
        # A's environment is intact and A can still list/test it.
        listed = client.get(f"/api/projects/{a['project_id']}/environments", headers=ha)
        assert listed.status_code == 200
        assert any(e["id"] == env for e in listed.json())
        assert client.post(f"/api/environments/{env}/test", headers=ha).status_code == 200

        # B cannot list A's project environments either.
        assert client.get(
            f"/api/projects/{a['project_id']}/environments", headers=hb).status_code == 404


def test_environment_by_id_flag_off_no_scoping(monkeypatch):
    """With multi-user OFF the env owner re-check is a no-op: a stray header
    never blocks single-user/Demo operation."""
    from app.main import app

    a = _seed(owner_id=None)
    stranger = {HEADER: _u("stranger")}

    with _multi_user(monkeypatch, False), TestClient(app) as client:
        env = _insert_env(a["project_id"])
        assert client.post(
            f"/api/environments/{env}/test", headers=stranger).status_code == 200
        assert client.get(
            f"/api/projects/{a['project_id']}/environments", headers=stranger).status_code == 200


def test_build_context_bad_mode_is_422_not_500(monkeypatch):
    """The build endpoint's `mode` query flows into the manifest's ContextMode
    enum. An unknown value must be rejected as 422 at the route, never surface
    as a 500 ValidationError; the two real build depths still work."""
    from app.main import app

    a = _seed(owner_id=None)

    with _multi_user(monkeypatch, False), TestClient(app) as client:
        r = client.post(f"/api/projects/{a['project_id']}/contexts/build", params={"mode": "bogus-mode"})
        assert r.status_code == 422, r.text
        for good in ("quick", "deep"):
            ok = client.post(f"/api/projects/{a['project_id']}/contexts/build", params={"mode": good})
            assert ok.status_code == 200, ok.text
