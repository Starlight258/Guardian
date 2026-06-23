"""Add community_summaries and entities.community_id for GraphRAG community summarization.

Revision ID: 0006_add_community_summaries
Revises: 0005_add_entity_graph_tables
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_add_community_summaries"
down_revision: str | None = "0005_add_entity_graph_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_summaries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    with op.batch_alter_table("entities") as batch_op:
        batch_op.add_column(sa.Column("community_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_entities_community_id", "community_summaries", ["community_id"], ["id"]
        )
    op.create_index("ix_entities_community_id", "entities", ["community_id"])


def downgrade() -> None:
    op.drop_index("ix_entities_community_id", table_name="entities")
    with op.batch_alter_table("entities") as batch_op:
        batch_op.drop_constraint("fk_entities_community_id", type_="foreignkey")
        batch_op.drop_column("community_id")
    op.drop_table("community_summaries")
