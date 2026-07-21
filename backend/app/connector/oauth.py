"""OAuth 2.0 client-credentials auth for Oracle EPM Cloud (OCI IAM domains).

OCI (Gen 2) EPM environments accept bearer tokens issued by the tenant's
OCI IAM identity domain in place of basic auth. The user registers a
*confidential application* in the identity domain, grants it access to the
EPM instance's resource scope, and supplies:

  * token URL  — ``https://idcs-<hash>.identity.oraclecloud.com/oauth2/v1/token``
  * client id / client secret of the confidential application
  * scope      — the EPM resource scope (e.g. ``https://<epm-app-id>...urn:opc:serviceInstanceID=...``)

Tokens are exchanged with ``grant_type=client_credentials``, cached until
shortly before expiry, registered with the redaction layer, and refreshed
once automatically when Oracle answers 401 (revoked/expired early).
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator

import httpx

from ..logging import get_logger
from ..security.redaction import register_secret
from .errors import ConnectorError, ErrorCategory
from .validation import validate_url

log = get_logger(__name__)

_TOKEN_SAFETY_WINDOW = 60.0  # refresh this many seconds before expiry
_DEFAULT_LIFETIME = 3600.0  # assumed lifetime when the response omits expires_in
_TOKEN_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


def _token_client() -> httpx.AsyncClient:
    """The client used for token exchange only (patchable in tests)."""
    return httpx.AsyncClient(timeout=_TOKEN_TIMEOUT)


class OAuthClientCredentials(httpx.Auth):
    """httpx auth that injects an IAM bearer token, refreshing as needed."""

    requires_response_body = False

    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str | None = None) -> None:
        if not (token_url or "").strip():
            raise ConnectorError(
                ErrorCategory.authentication,
                "An OAuth token URL is required.",
                suggested_action="Enter the identity domain token URL "
                                 "(https://idcs-…identity.oraclecloud.com/oauth2/v1/token).",
            )
        if not (client_id or "").strip():
            raise ConnectorError(
                ErrorCategory.authentication,
                "An OAuth client ID is required.",
                suggested_action="Enter the confidential application's client ID.",
            )
        if not (client_secret or "").strip():
            raise ConnectorError(
                ErrorCategory.authentication,
                "An OAuth client secret is required.",
                suggested_action="Enter the confidential application's client secret.",
            )
        try:
            self.token_url = validate_url(token_url)
        except ConnectorError as exc:
            raise ConnectorError(
                ErrorCategory.invalid_argument,
                "The OAuth token URL is not a valid http(s) URL.",
                suggested_action="Enter the identity domain token URL "
                                 "(https://idcs-…identity.oraclecloud.com/oauth2/v1/token).",
            ) from exc
        self.client_id = client_id.strip()
        self._client_secret = client_secret
        register_secret(client_secret)
        self.scope = (scope or "").strip()
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._bearer_token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401:
            # Token revoked or expired ahead of schedule: refresh once and retry.
            token = await self._bearer_token(force=True)
            request.headers["Authorization"] = f"Bearer {token}"
            yield request

    async def _bearer_token(self, force: bool = False) -> str:
        if not force and self._token and time.monotonic() < self._token_expires_at - _TOKEN_SAFETY_WINDOW:
            return self._token
        data = {"grant_type": "client_credentials"}
        if self.scope:
            data["scope"] = self.scope
        try:
            async with _token_client() as client:
                resp = await client.post(
                    self.token_url,
                    data=data,
                    auth=(self.client_id, self._client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.ConnectError as exc:
            raise ConnectorError(
                ErrorCategory.connectivity,
                "Could not reach the OAuth token endpoint.",
                suggested_action="Check the identity domain token URL and your network.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(
                ErrorCategory.connectivity, f"OAuth token exchange failed: {type(exc).__name__}."
            ) from exc
        if resp.status_code in (400, 401, 403):
            raise ConnectorError(
                ErrorCategory.authentication,
                "The identity domain rejected the OAuth client credentials.",
                suggested_action="Check the client ID, client secret and scope, then retry.",
            )
        if resp.status_code >= 400:
            raise ConnectorError(
                ErrorCategory.authentication,
                f"OAuth token endpoint returned HTTP {resp.status_code}.",
                technical_detail=resp.text[:300],
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ConnectorError(
                ErrorCategory.authentication, "The OAuth token endpoint returned a non-JSON response."
            ) from exc
        token = payload.get("access_token")
        if not token:
            raise ConnectorError(
                ErrorCategory.authentication, "The OAuth token response did not contain an access token."
            )
        register_secret(token)
        try:
            lifetime = float(payload.get("expires_in", _DEFAULT_LIFETIME))
        except (TypeError, ValueError):
            lifetime = _DEFAULT_LIFETIME
        self._token = token
        self._token_expires_at = time.monotonic() + lifetime
        log.info("oauth_token_acquired", token_url=self.token_url, lifetime=lifetime)
        return token
