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

# Keys whose values are always redacted in structured payloads (exact match).
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

# High-signal substrings so prefixed/nested keys (db_password, oracle_password,
# x_api_key, client_secret) are also redacted. Chosen to avoid collisions with
# benign words like "author"/"session" (those stay exact-match only).
_SENSITIVE_KEY_SUBSTRINGS = (
    "password", "passwd", "pwd", "secret", "token", "apikey", "api_key",
    "credential", "private_key", "access_key",
)

# The `key: value` prose pattern accepts an optionally quoted value so secrets
# containing spaces ("the password is hunter2 with spaces") are still caught.
_KV_VALUE = r"(?:\"[^\"]{4,}\"|'[^']{4,}'|[^\s,;\"']{4,})"

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"\bgh[posru]_[A-Za-z0-9]{20,}\b"),  # GitHub PAT/OAuth/refresh tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}"),  # JWT
    re.compile(rf"(?i)\b(?:api[_-]?key|password|passwd|pwd|token|secret)\b\s*(?:is\s+)?[:=]?\s*{_KV_VALUE}"),
    # user[:pass]@host in a URL — userinfo may itself contain '@' (email usernames),
    # so match greedily up to the last '@' before the host/path.
    re.compile(r"(?i)(https?://)[^/\s]*@"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]
_URL_CRED_PATTERN = _PATTERNS[-2]

# Used by looks_like_secret to warn a user who pastes a credential into chat.
_SECRET_HINTS: list[re.Pattern[str]] = [
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"\bgh[posru]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bpassword\b\s*(?:is\s+)?[:=]?\s*\S{4,}"),
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
        if pat is _URL_CRED_PATTERN:
            out = pat.sub(rf"\1{REDACTION}@", out)  # keep scheme + host, drop userinfo
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


def _is_sensitive_key(key: str) -> bool:
    kl = key.lower()
    return kl in SENSITIVE_KEYS or any(tok in kl for tok in _SENSITIVE_KEY_SUBSTRINGS)


def redact_mapping(data: dict) -> dict:
    out: dict = {}
    for k, v in data.items():
        if isinstance(k, str) and _is_sensitive_key(k):
            out[k] = REDACTION
        else:
            out[k] = redact_value(v)
    return out


def looks_like_secret(text: str) -> bool:
    """Heuristic: does a user's chat message appear to contain a credential?"""
    if not text:
        return False
    return any(p.search(text) for p in _SECRET_HINTS)
