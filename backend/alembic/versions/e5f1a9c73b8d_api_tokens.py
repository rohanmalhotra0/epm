"""api_tokens (personal API tokens for the browser-agent extension)

Adds the ``api_tokens`` table backing autonomous (token-authenticated) access to
the ``/api/ext`` routes. Only the SHA-256 hash of each token is stored; the
plaintext is shown to the user once at creation. Owner-scoped via ``owner_id``.

Defensive/idempotent: only creates the table when missing, so it is a safe
no-op on databases whose schema already has it.

Revision ID: e5f1a9c73b8d
Revises: d4e8a7c15f2b
Create Date: 2026-07-22 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e5f1a9c73b8d'
down_revision: str | None = 'd4e8a7c15f2b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("api_tokens"):
        return
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default="Browser agent"),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # Inline so SQLite (which can't ALTER-ADD a constraint) builds it with
        # the table. The unique constraint also provides the lookup index.
        sa.UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
    )
    op.create_index("ix_api_tokens_owner_id", "api_tokens", ["owner_id"])


def downgrade() -> None:
    if not _has_table("api_tokens"):
        return
    op.drop_index("ix_api_tokens_owner_id", table_name="api_tokens")
    op.drop_table("api_tokens")
