"""Add sources.file_mtime for mtime-based reindex skip.

Revision ID: 0004_add_sources_file_mtime
Revises: 0003_add_sources_session_id
Create Date: 2026-05-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_sources_file_mtime"
down_revision: str | None = "0003_add_sources_session_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("file_mtime", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "file_mtime")
