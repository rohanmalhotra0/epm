"""project owner_id (multi-user owner-scoping)

Adds a nullable ``owner_id`` column (plus index) to ``projects`` for optional
multi-user owner-scoping. Default-OFF: single-user / Demo installs keep the
sentinel "local" owner, and the app's behavior is unchanged.

The column is also present in freshly-generated initial schemas, so this
migration is defensive: it only adds the column / index when missing, making it
a safe no-op on databases whose initial migration already created them. Existing
NULL-owner rows are backfilled to "local" (legacy rows stay visible to all at
the application layer regardless).

Revision ID: c9d3f1a2b4e7
Revises: 8b17d4e2a951
Create Date: 2026-07-21 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c9d3f1a2b4e7'
down_revision: str | None = '8b17d4e2a951'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns("projects")}


def _existing_indexes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {ix["name"] for ix in inspector.get_indexes("projects")}


def upgrade() -> None:
    if "owner_id" not in _existing_columns():
        op.add_column("projects", sa.Column("owner_id", sa.String(length=120), nullable=True))
    if "ix_projects_owner_id" not in _existing_indexes():
        op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    # Backfill legacy rows to the single-user "local" owner.
    op.execute("UPDATE projects SET owner_id='local' WHERE owner_id IS NULL")


def downgrade() -> None:
    if "ix_projects_owner_id" in _existing_indexes():
        op.drop_index("ix_projects_owner_id", table_name="projects")
    with op.batch_alter_table("projects") as batch_op:
        if "owner_id" in _existing_columns():
            batch_op.drop_column("owner_id")
