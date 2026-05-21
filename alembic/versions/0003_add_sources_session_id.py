"""Add sources.session_id for session checkpoints.

Revision ID: 0003_add_sources_session_id
Revises: 0002_drop_sources_is_deleted
Create Date: 2026-05-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_sources_session_id"
down_revision: str | None = "0002_drop_sources_is_deleted"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("session_id", sa.String(length=64), nullable=True))
    op.create_index("ix_sources_session_id", "sources", ["session_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sources_session_id", table_name="sources")
    op.drop_column("sources", "session_id")
