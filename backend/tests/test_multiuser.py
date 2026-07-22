"""Multi-user owner-scoping (default OFF = zero behavior change).

Covers config.Settings.multi_user, deps.get_current_owner + require_project
enforcement, and the owner-threaded project services / routes.
"""

from __future__ import annotations

import contextlib

from fastapi.testclient import TestClient

import app.config
from app.db.base import get_sessionmaker
from app.db.models import Project

ALICE = "alice@example.com"
BOB = "bob@example.com"
HEADER = "X-Forwarded-Email"


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


def _insert_null_owner_project(name: str) -> str:
    """Insert a legacy project with NULL owner directly (bypassing the service)."""
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        p = Project(name=name, description=None, is_default=False, owner_id=None)
        s.add(p)
        s.commit()
        return p.id
    finally:
        s.close()


def test_multi_user_off_ignores_headers(monkeypatch):
    """Default OFF: identity headers are ignored, everything is the "local" owner."""
    from app.main import app

    with _multi_user(monkeypatch, False), TestClient(app) as client:
        created = client.post(
            "/api/projects",
            json={"name": "MU-off project"},
            headers={HEADER: ALICE},
        )
        assert created.status_code == 201
        pid = created.json()["id"]
        # owner_id is internal — never leaked into ProjectOut.
        assert "ownerId" not in created.json() and "owner_id" not in created.json()

        # A different identity still sees the project (headers ignored when off).
        listed = client.get("/api/projects", headers={HEADER: BOB}).json()
        assert any(p["id"] == pid for p in listed)

    # Persisted owner is the "local" sentinel, not the header value.
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        assert s.get(Project, pid).owner_id == "local"
    finally:
        s.close()


def test_multi_user_on_scopes_by_owner(monkeypatch):
    from app.main import app

    null_pid = _insert_null_owner_project("Legacy shared project")

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        alice_pid = client.post(
            "/api/projects", json={"name": "Alice project"}, headers={HEADER: ALICE}
        ).json()["id"]
        bob_pid = client.post(
            "/api/projects", json={"name": "Bob project"}, headers={HEADER: BOB}
        ).json()["id"]

        alice_ids = {p["id"] for p in client.get("/api/projects", headers={HEADER: ALICE}).json()}
        bob_ids = {p["id"] for p in client.get("/api/projects", headers={HEADER: BOB}).json()}

        # Each identity sees only its own projects.
        assert alice_pid in alice_ids and bob_pid not in alice_ids
        assert bob_pid in bob_ids and alice_pid not in bob_ids

        # The "local"-owned seeded default project is not visible to either.
        # Legacy NULL-owner project is visible to BOTH.
        assert null_pid in alice_ids and null_pid in bob_ids

        # Cross-owner get by id -> 404.
        assert client.get(f"/api/projects/{bob_pid}", headers={HEADER: ALICE}).status_code == 404
        assert client.get(f"/api/projects/{alice_pid}", headers={HEADER: BOB}).status_code == 404

        # Own get -> 200; legacy NULL-owner get visible to both -> 200.
        assert client.get(f"/api/projects/{alice_pid}", headers={HEADER: ALICE}).status_code == 200
        assert client.get(f"/api/projects/{null_pid}", headers={HEADER: ALICE}).status_code == 200
        assert client.get(f"/api/projects/{null_pid}", headers={HEADER: BOB}).status_code == 200


def test_multi_user_on_missing_header_falls_back_to_local(monkeypatch):
    from app.main import app

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        # No identity header -> "local" owner; sees the seeded local default project.
        listed = client.get("/api/projects").json()
        assert any(p["isDefault"] for p in listed)


def test_get_current_owner_unit(monkeypatch):
    from starlette.requests import Request

    from app.api.deps import get_current_owner

    def _req(headers: dict) -> Request:
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
        return Request(scope)

    with _multi_user(monkeypatch, False):
        assert get_current_owner(_req({HEADER: ALICE})) == "local"

    with _multi_user(monkeypatch, True):
        assert get_current_owner(_req({HEADER: ALICE})) == ALICE
        assert get_current_owner(_req({})) == "local"


def test_service_defaults_are_local(session):
    """Existing callers that don't pass owner still work = "local"."""
    from app.services import projects as svc

    out = svc.create_project(session, "Default-owner service project")
    session.flush()
    assert session.get(Project, out.id).owner_id == "local"

    # list/get_default default owner filters include local + NULL rows.
    ids = {p.id for p in svc.list_projects(session)}
    assert out.id in ids
    assert svc.get_default_project(session) is not None


def test_multi_user_auto_provisions_project_for_new_user(monkeypatch):
    """A Google-authenticated user with no projects gets one on first list —
    without it the UI has no project and 'New chat' silently no-ops."""
    from app.main import app

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        # Earlier tests leave NULL-owner legacy rows (visible to everyone),
        # which would satisfy the "has projects" check and mask provisioning.
        SessionLocal = get_sessionmaker()
        s = SessionLocal()
        try:
            s.query(Project).filter(Project.owner_id.is_(None)).delete()
            s.query(Project).filter(Project.owner_id.in_([ALICE, BOB])).delete()
            s.commit()
        finally:
            s.close()

        first = client.get("/api/projects", headers={HEADER: ALICE})
        assert first.status_code == 200
        projects = first.json()
        assert len(projects) >= 1
        pid = projects[0]["id"]

        # Idempotent: listing again returns the same project, not a duplicate.
        again = client.get("/api/projects", headers={HEADER: ALICE})
        assert [p["id"] for p in again.json()] == [p["id"] for p in projects]

        # Scoped: BOB does not see ALICE's auto-provisioned project.
        bob = client.get("/api/projects", headers={HEADER: BOB})
        assert pid not in [p["id"] for p in bob.json()]
