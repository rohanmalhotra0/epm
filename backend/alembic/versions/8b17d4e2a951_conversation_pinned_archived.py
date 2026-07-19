"""conversation pinned/archived flags

Adds the ``pinned`` and ``archived`` boolean columns to ``conversations`` for
conversation management (pin to top of list, archive out of the default list).

The columns are also present in freshly-generated initial schemas, so this
migration is defensive: it only adds a column when it is missing, making it a
safe no-op on databases whose initial migration already created them.

Revision ID: 8b17d4e2a951
Revises: 24c767b4fc2d
Create Date: 2026-07-19 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '8b17d4e2a951'
down_revision: str | None = '24c767b4fc2d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns("conversations")}


def upgrade() -> None:
    existing = _existing_columns()
    if "pinned" not in existing:
        op.add_column(
            "conversations",
            sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "archived" not in existing:
        op.add_column(
            "conversations",
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    existing = _existing_columns()
    with op.batch_alter_table("conversations") as batch_op:
        if "archived" in existing:
            batch_op.drop_column("archived")
        if "pinned" in existing:
            batch_op.drop_column("pinned")
