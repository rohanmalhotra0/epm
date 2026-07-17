"""Security singletons: encrypted secret store + in-memory session cache."""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .redaction import looks_like_secret, redact_mapping, redact_text, register_secret
from .secrets import EncryptedSecretStore, ProcessSecretCache

_process_cache: ProcessSecretCache | None = None


@lru_cache
def get_secret_store() -> EncryptedSecretStore:
    settings = get_settings()
    return EncryptedSecretStore(settings.secrets_dir, settings.secret_master_key)


def get_process_secrets() -> ProcessSecretCache:
    global _process_cache
    if _process_cache is None:
        _process_cache = ProcessSecretCache()
    return _process_cache


__all__ = [
    "get_secret_store",
    "get_process_secrets",
    "redact_text",
    "redact_mapping",
    "register_secret",
    "looks_like_secret",
]
