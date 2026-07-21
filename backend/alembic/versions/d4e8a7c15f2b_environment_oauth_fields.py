"""environment OAuth 2.0 client-credentials fields

Adds ``oauth_token_url``, ``oauth_client_id`` and ``oauth_scope`` to
``environment_profiles`` so an environment can authenticate to Oracle EPM
via an OCI IAM identity domain confidential application instead of a
username/password. The client secret is never stored in the database.

The columns are also present in freshly-generated initial schemas, so this
migration is defensive: it only adds a column when it is missing, making it a
safe no-op on databases whose initial migration already created them.

Revision ID: d4e8a7c15f2b
Revises: c9d3f1a2b4e7
Create Date: 2026-07-21 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd4e8a7c15f2b'
down_revision: str | None = 'c9d3f1a2b4e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = {
    "oauth_token_url": sa.String(length=400),
    "oauth_client_id": sa.String(length=200),
    "oauth_scope": sa.String(length=400),
}


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns("environment_profiles")}


def upgrade() -> None:
    existing = _existing_columns()
    for name, type_ in _COLUMNS.items():
        if name not in existing:
            op.add_column("environment_profiles", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    existing = _existing_columns()
    with op.batch_alter_table("environment_profiles") as batch_op:
        for name in _COLUMNS:
            if name in existing:
                batch_op.drop_column(name)
