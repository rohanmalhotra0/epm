"""EPM connector boundary (spec section 14)."""

from __future__ import annotations

from .base import ConnectorInfo, EpmConnector, JobResult
from .demo import DemoConnector, register_deployed_form, reset_demo_state
from .errors import ConnectorError, ErrorCategory
from .factory import ConnectionRegistry, get_registry

__all__ = [
    "EpmConnector",
    "ConnectorInfo",
    "JobResult",
    "DemoConnector",
    "register_deployed_form",
    "reset_demo_state",
    "ConnectorError",
    "ErrorCategory",
    "ConnectionRegistry",
    "get_registry",
]
