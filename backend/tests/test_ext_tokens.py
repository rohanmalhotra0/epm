"""API tokens + the token-gated /api/ext routes (autonomous extension auth)."""

from __future__ import annotations

import contextlib

from fastapi.testclient import TestClient

import app.config
from app.db.base import get_sessionmaker
from app.services import api_tokens as tokens_svc

ALICE = "alice@example.com"
BOB = "bob@example.com"
HEADER = "X-Forwarded-Email"


@contextlib.contextmanager
def _multi_user(monkeypatch, enabled: bool):
    monkeypatch.setenv("EPMW_MULTI_USER", "true" if enabled else "false")
    app.config.get_settings.cache_clear()
    try:
        yield
    finally:
        monkeypatch.delenv("EPMW_MULTI_USER", raising=False)
        app.config.get_settings.cache_clear()


def test_create_list_revoke_token(monkeypatch):
    from app.main import app

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        created = client.post("/api/ext-tokens", json={"name": "My laptop"},
                              headers={HEADER: ALICE})
        assert created.status_code == 201
        body = created.json()
        assert body["token"].startswith("epmw_")
        assert body["prefix"] == body["token"][:11]
        assert body["name"] == "My laptop"
        tid = body["id"]

        # Listed for alice, not leaking the secret.
        listed = client.get("/api/ext-tokens", headers={HEADER: ALICE})
        assert listed.status_code == 200
        rows = listed.json()
        assert any(r["id"] == tid for r in rows)
        assert all("token" not in r for r in rows)

        # Bob cannot see alice's token.
        assert client.get("/api/ext-tokens", headers={HEADER: BOB}).json() == []

        # Revoke, then it's gone from the list.
        assert client.delete(f"/api/ext-tokens/{tid}", headers={HEADER: ALICE}).status_code == 204
        assert all(r["id"] != tid for r in client.get("/api/ext-tokens", headers={HEADER: ALICE}).json())

        # Bob cannot revoke someone else's token (404, not 204).
        again = client.post("/api/ext-tokens", json={}, headers={HEADER: ALICE}).json()
        assert client.delete(f"/api/ext-tokens/{again['id']}", headers={HEADER: BOB}).status_code == 404


def test_ext_whoami_requires_valid_token(monkeypatch):
    from app.main import app

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        token = client.post("/api/ext-tokens", json={}, headers={HEADER: ALICE}).json()["token"]

        # No token → 401. A spoofed identity header must be IGNORED here.
        assert client.get("/api/ext/whoami").status_code == 401
        assert client.get("/api/ext/whoami", headers={HEADER: ALICE}).status_code == 401
        assert client.get("/api/ext/whoami",
                          headers={"Authorization": "Bearer epmw_bogus"}).status_code == 401

        # Valid token → owner is the token's owner, not any header.
        ok = client.get("/api/ext/whoami",
                        headers={"Authorization": f"Bearer {token}", HEADER: BOB})
        assert ok.status_code == 200
        assert ok.json()["owner"] == ALICE


def test_revoked_token_is_rejected(monkeypatch):
    from app.main import app

    with _multi_user(monkeypatch, True), TestClient(app) as client:
        made = client.post("/api/ext-tokens", json={}, headers={HEADER: ALICE}).json()
        token, tid = made["token"], made["id"]
        assert client.get("/api/ext/whoami",
                          headers={"Authorization": f"Bearer {token}"}).status_code == 200
        client.delete(f"/api/ext-tokens/{tid}", headers={HEADER: ALICE})
        assert client.get("/api/ext/whoami",
                          headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_ext_routes_local_when_multi_user_off(monkeypatch):
    """Single-user installs: /api/ext works as the local owner with no token."""
    from app.main import app

    with _multi_user(monkeypatch, False), TestClient(app) as client:
        r = client.get("/api/ext/whoami")
        assert r.status_code == 200
        assert r.json()["owner"] == "local"


def test_ext_spreadsheet_inspect_requires_token(monkeypatch):
    """The autonomous workbook-inspect route is token-gated like the agent one."""
    from app.main import app

    csv = ("wb.csv", "a,b\n1,2\n", "text/csv")
    with _multi_user(monkeypatch, True), TestClient(app) as client:
        token = client.post("/api/ext-tokens", json={}, headers={HEADER: ALICE}).json()["token"]

        # No token → 401 (identity header ignored on the ungated path).
        r = client.post("/api/ext/spreadsheet/inspect",
                        files={"file": csv}, headers={HEADER: ALICE})
        assert r.status_code == 401

        # Valid token → parses and returns an inspection.
        ok = client.post("/api/ext/spreadsheet/inspect",
                         files={"file": csv}, headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200


def test_resolve_owner_unit():
    """Service-level: hashing round-trips and revocation/unknown tokens fail."""
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        row, plaintext = tokens_svc.create_token(s, ALICE, "unit")
        s.commit()
        assert tokens_svc.resolve_owner(s, plaintext) == ALICE
        assert tokens_svc.resolve_owner(s, "epmw_nope") is None
        assert tokens_svc.resolve_owner(s, "not-a-token") is None
        tokens_svc.revoke_token(s, ALICE, row.id)
        s.commit()
        assert tokens_svc.resolve_owner(s, plaintext) is None
    finally:
        s.close()
