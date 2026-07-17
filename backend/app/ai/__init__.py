"""Provider-independent AI layer (spec section 11)."""

from __future__ import annotations

from .base import (
    AIMessage,
    AIProvider,
    ProviderConfig,
    ProviderError,
    StreamChunk,
    StreamDone,
    TextDelta,
    Usage,
)
from .mock import MockProvider
from .registry import provider_from_profile, resolve_active_provider

__all__ = [
    "AIMessage",
    "AIProvider",
    "ProviderConfig",
    "ProviderError",
    "StreamChunk",
    "StreamDone",
    "TextDelta",
    "Usage",
    "MockProvider",
    "provider_from_profile",
    "resolve_active_provider",
]
