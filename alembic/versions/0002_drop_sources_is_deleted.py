"""Drop sources.is_deleted — hard delete replaces soft delete.

Revision ID: 0002_drop_sources_is_deleted
Revises: 0001_initial_schema
Create Date: 2026-05-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_drop_sources_is_deleted"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_column("is_deleted")


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false())
        )
