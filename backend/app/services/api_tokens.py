"""Personal API tokens for the browser-agent extension (autonomous auth).

Tokens are opaque bearer strings of the form ``epmw_<random>``. Only their
SHA-256 hash is stored; the plaintext is returned to the caller exactly once at
creation. Resolution is constant-time-ish via a hash lookup and is owner-scoped
by the token's ``owner_id``.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from ..db.base import utcnow
from ..db.models import ApiToken

TOKEN_PREFIX = "epmw_"
# Bytes of entropy in the random part (43 url-safe chars ≈ 256 bits).
_ENTROPY_BYTES = 32
_LAST_USED_WRITE_INTERVAL = timedelta(minutes=5)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _display_prefix(token: str) -> str:
    # e.g. "epmw_ab12cd" — non-secret, enough to tell tokens apart in a list.
    return token[: len(TOKEN_PREFIX) + 6]


def create_token(session: Session, owner: str, name: str | None = None) -> tuple[ApiToken, str]:
    """Mint a token for ``owner``. Returns (row, plaintext). The plaintext is the
    ONLY time the secret exists outside the user's hands — it is never stored."""
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(_ENTROPY_BYTES)
    row = ApiToken(
        owner_id=owner,
        name=(name or "Browser agent").strip()[:120] or "Browser agent",
        token_hash=_hash(plaintext),
        prefix=_display_prefix(plaintext),
    )
    session.add(row)
    session.flush()
    return row, plaintext


def list_tokens(session: Session, owner: str) -> list[ApiToken]:
    return (
        session.query(ApiToken)
        .filter(ApiToken.owner_id == owner, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
        .all()
    )


def revoke_token(session: Session, owner: str, token_id: str) -> bool:
    row = session.get(ApiToken, token_id)
    if row is None or row.owner_id != owner or row.revoked_at is not None:
        return False
    row.revoked_at = utcnow()
    session.flush()
    return True


def resolve_owner(session: Session, token: str) -> str | None:
    """Return the owner for a valid, non-revoked token, or None. Updates
    ``last_used_at`` on success (best-effort)."""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    row = (
        session.query(ApiToken)
        .filter(ApiToken.token_hash == _hash(token), ApiToken.revoked_at.is_(None))
        .first()
    )
    if row is None:
        return None
    now = utcnow()
    if row.last_used_at is None or now - row.last_used_at >= _LAST_USED_WRITE_INTERVAL:
        row.last_used_at = now
    return row.owner_id
