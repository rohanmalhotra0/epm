"""Connector factory + in-process connection registry.

Passwords for live environments are held only in process memory (spec section 13,
step 7) unless the user explicitly asks to remember them, in which case they go
to the encrypted local secret store — never to SQLite, never to the model.
"""

from __future__ import annotations

import threading

from ..config import get_settings
from ..db.models import EnvironmentProfile
from ..logging import get_logger
from ..security import get_process_secrets, get_secret_store
from ..security.redaction import register_secret
from .base import EpmConnector
from .demo import DemoConnector
from .epm_automate import EpmAutomateRunner
from .errors import ConnectorError, ErrorCategory
from .oauth import OAuthClientCredentials
from .oracle_rest import OracleRestConnector

log = get_logger(__name__)
SECRET_NS = "environment"
OAUTH_METHOD = "oauthClientCredentials"


class ConnectionRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, EpmConnector] = {}
        self._lock = threading.RLock()

    def is_connected(self, environment_id: str) -> bool:
        with self._lock:
            conn = self._connectors.get(environment_id)
            return bool(conn and conn.info.connected)

    def get(self, environment_id: str) -> EpmConnector | None:
        with self._lock:
            return self._connectors.get(environment_id)

    def get_or_demo(self, env: EnvironmentProfile) -> EpmConnector:
        """Return the active connector, or a demo connector for demo environments."""
        conn = self.get(env.id)
        if conn is not None:
            return conn
        if env.demo:
            demo = DemoConnector(classification=env.classification, application=env.preferred_application or "MCWPCF")
            with self._lock:
                self._connectors[env.id] = demo
            return demo
        raise ConnectorError(
            ErrorCategory.authentication,
            f"Environment '{env.name}' is not connected.",
            suggested_action="Connect to the environment before running this action.",
        )

    async def connect(
        self, env: EnvironmentProfile, password: str | None = None, remember: bool = False
    ) -> EpmConnector:
        if env.demo:
            connector: EpmConnector = DemoConnector(
                classification=env.classification, application=env.preferred_application or "MCWPCF"
            )
            await connector.login()
            with self._lock:
                self._connectors[env.id] = connector
            return connector

        # The stored secret is the Oracle password, or — for an OAuth
        # environment — the confidential application's client secret.
        oauth_env = env.auth_method == OAUTH_METHOD
        pwd = password or get_process_secrets().get(SECRET_NS, env.id) or get_secret_store().get(SECRET_NS, env.id)
        if not pwd:
            raise ConnectorError(
                ErrorCategory.authentication,
                "A client secret is required to connect to this environment."
                if oauth_env else "A password is required to connect to this environment.",
                suggested_action="Enter the OAuth client secret to connect."
                if oauth_env else "Enter your Oracle password to connect.",
            )
        register_secret(pwd)
        settings = get_settings()
        oauth = None
        if oauth_env:
            oauth = OAuthClientCredentials(
                token_url=env.oauth_token_url or "",
                client_id=env.oauth_client_id or "",
                client_secret=pwd,
                scope=env.oauth_scope,
            )
        connector = OracleRestConnector(
            base_url=env.base_url or "",
            username=env.username or "",
            password="" if oauth_env else pwd,
            classification=env.classification,
            application=env.preferred_application,
            runner=EpmAutomateRunner(),
            metadata_job=settings.oracle_metadata_job,
            metadata_snapshot=settings.oracle_metadata_snapshot,
            oauth=oauth,
        )
        await connector.login()  # harmless read-only auth check
        # Keep the password only where the user asked.
        get_process_secrets().set(SECRET_NS, env.id, pwd)
        if remember:
            get_secret_store().set(SECRET_NS, env.id, pwd)
        with self._lock:
            self._connectors[env.id] = connector
        return connector

    def disconnect(self, environment_id: str) -> None:
        with self._lock:
            conn = self._connectors.pop(environment_id, None)
        if conn is not None:
            conn.info.connected = False
        get_process_secrets().delete(SECRET_NS, environment_id)


_registry: ConnectionRegistry | None = None


def get_registry() -> ConnectionRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectionRegistry()
    return _registry
