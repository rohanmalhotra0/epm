"""OAuth 2.0 client-credentials auth for the Oracle connector.

Everything runs offline against httpx.MockTransport — no Oracle or IAM
endpoint is ever contacted.
"""

from __future__ import annotations

import httpx
import pytest

from app.connector.errors import ConnectorError, ErrorCategory
from app.connector.oauth import OAuthClientCredentials
from app.connector.oracle_rest import OracleRestConnector

TOKEN_URL = "https://idcs-abc.identity.oraclecloud.com/oauth2/v1/token"
EPM_URL = "https://planning-test-pod.epm.us.oraclecloud.com"


def _oauth(**overrides) -> OAuthClientCredentials:
    kwargs = {"token_url": TOKEN_URL, "client_id": "cid", "client_secret": "shh", "scope": "urn:opc:epm"}
    kwargs.update(overrides)
    return OAuthClientCredentials(**kwargs)


def _patch_token_endpoint(monkeypatch, handler) -> list[httpx.Request]:
    """Route the auth's internal token client through a MockTransport."""
    import app.connector.oauth as oauth_mod

    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        oauth_mod, "_token_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    )
    return seen


def _token_response(request: httpx.Request, token: str = "tok-1", expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(200, json={"access_token": token, "expires_in": expires_in})


# --- configuration validation ------------------------------------------------


def test_missing_fields_raise_clear_authentication_errors():
    for missing in ("token_url", "client_id", "client_secret"):
        with pytest.raises(ConnectorError) as err:
            _oauth(**{missing: ""})
        assert err.value.category in (ErrorCategory.authentication, ErrorCategory.invalid_argument)


def test_invalid_token_url_is_rejected():
    with pytest.raises(ConnectorError) as err:
        _oauth(token_url="idcs-abc oauth2 token")
    assert err.value.category == ErrorCategory.invalid_argument


# --- token exchange ----------------------------------------------------------


async def test_token_exchange_sends_client_credentials_grant(monkeypatch):
    auth = _oauth()
    seen = _patch_token_endpoint(monkeypatch, _token_response)

    token = await auth._bearer_token()
    assert token == "tok-1"
    req = seen[0]
    assert str(req.url) == TOKEN_URL
    body = req.content.decode()
    assert "grant_type=client_credentials" in body
    assert "scope=urn%3Aopc%3Aepm" in body
    # Client id/secret travel as HTTP basic auth, not in the form body.
    assert req.headers["Authorization"].startswith("Basic ")
    assert "shh" not in body


async def test_token_is_cached_until_expiry(monkeypatch):
    auth = _oauth()
    seen = _patch_token_endpoint(monkeypatch, _token_response)
    assert await auth._bearer_token() == "tok-1"
    assert await auth._bearer_token() == "tok-1"
    assert len(seen) == 1  # second call served from cache
    assert await auth._bearer_token(force=True) == "tok-1"
    assert len(seen) == 2


async def test_rejected_credentials_surface_as_authentication_error(monkeypatch):
    auth = _oauth()
    _patch_token_endpoint(monkeypatch, lambda req: httpx.Response(401, json={"error": "invalid_client"}))
    with pytest.raises(ConnectorError) as err:
        await auth._bearer_token()
    assert err.value.category == ErrorCategory.authentication


async def test_non_json_token_response_is_an_error(monkeypatch):
    auth = _oauth()
    _patch_token_endpoint(monkeypatch, lambda req: httpx.Response(200, text="<html>login</html>"))
    with pytest.raises(ConnectorError) as err:
        await auth._bearer_token()
    assert err.value.category == ErrorCategory.authentication


# --- request auth flow -------------------------------------------------------


async def test_requests_carry_bearer_token_and_refresh_once_on_401(monkeypatch):
    auth = _oauth()
    tokens = iter(["tok-1", "tok-2", "tok-3"])
    _patch_token_endpoint(monkeypatch, lambda req: _token_response(req, token=next(tokens)))

    api_calls: list[str] = []

    def api(request: httpx.Request) -> httpx.Response:
        bearer = request.headers.get("Authorization", "")
        api_calls.append(bearer)
        # First token is treated as revoked: force the one-shot refresh path.
        if bearer == "Bearer tok-1":
            return httpx.Response(401)
        return httpx.Response(200, json={"items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(api), auth=auth, base_url=EPM_URL) as client:
        resp = await client.get("/HyperionPlanning/rest/v3/applications")

    assert resp.status_code == 200
    assert api_calls == ["Bearer tok-1", "Bearer tok-2"]


# --- connector wiring --------------------------------------------------------


def test_connector_uses_oauth_and_disables_password_only_features():
    conn = OracleRestConnector(base_url=EPM_URL, oauth=_oauth())
    assert conn._client().auth is conn._oauth
    # EPM Automate member export needs a password; OAuth-only degrades gracefully.
    assert conn._can_export_members is False


def test_connector_requires_some_credential():
    with pytest.raises(ConnectorError) as err:
        OracleRestConnector(base_url=EPM_URL)
    assert err.value.category == ErrorCategory.authentication


def test_connector_still_accepts_basic_auth():
    conn = OracleRestConnector(base_url=EPM_URL, username="u", password="p")
    client = conn._client()
    assert isinstance(client.auth, httpx.BasicAuth)
