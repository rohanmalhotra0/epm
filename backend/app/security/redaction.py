"""Centralised secret redaction (spec section 12).

Every log line, tool result, error message and diagnostic bundle is passed
through :func:`redact_text`. Exact known secrets (a password entered this
session, an API key) are additionally registered so they are scrubbed verbatim
even when they don't match a generic pattern.

Secrets must never reach the model, logs, chat history, context packages,
generated artifacts or git.
"""

from __future__ import annotations

import re
import threading

REDACTION = "«redacted»"

# Exact secret strings registered at runtime (passwords, tokens, keys).
_known_secrets: set[str] = set()
_lock = threading.Lock()

# Keys whose values are always redacted in structured payloads.
SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "cookie",
    "set-cookie",
    "session",
    "private_key",
    "client_secret",
    "encryption_key",
    "master_key",
}

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|passwd|pwd|token|secret)\b\s*[:=]\s*[^\s,;\"']{4,}"),
    # user:pass@host in a URL
    re.compile(r"(?i)(https?://[^/\s:@]+):([^/\s:@]+)@"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]

# Used by looks_like_secret to warn a user who pastes a credential into chat.
_SECRET_HINTS: list[re.Pattern[str]] = [
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bpassword\b\s*[:=]\s*\S{4,}"),
]


def register_secret(value: str | None) -> None:
    """Register an exact secret to scrub from all future output."""
    if value and len(value) >= 4:
        with _lock:
            _known_secrets.add(value)


def unregister_secret(value: str | None) -> None:
    if value:
        with _lock:
            _known_secrets.discard(value)


def clear_registered_secrets() -> None:
    with _lock:
        _known_secrets.clear()


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    with _lock:
        secrets = sorted(_known_secrets, key=len, reverse=True)
    for s in secrets:
        if s in out:
            out = out.replace(s, REDACTION)
    for pat in _PATTERNS:
        if pat.pattern.startswith("(?i)(https"):
            out = pat.sub(rf"\1:{REDACTION}@", out)
        else:
            out = pat.sub(REDACTION, out)
    return out


def redact_value(value):  # noqa: ANN001
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, (list, tuple)):
        return type(value)(redact_value(v) for v in value)
    return value


def redact_mapping(data: dict) -> dict:
    out: dict = {}
    for k, v in data.items():
        if isinstance(k, str) and k.lower() in SENSITIVE_KEYS:
            out[k] = REDACTION
        else:
            out[k] = redact_value(v)
    return out


def looks_like_secret(text: str) -> bool:
    """Heuristic: does a user's chat message appear to contain a credential?"""
    if not text:
        return False
    return any(p.search(text) for p in _SECRET_HINTS)
