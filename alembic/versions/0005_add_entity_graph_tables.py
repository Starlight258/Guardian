"""Add entities, chunk_entities, entity_relations for GraphRAG entity graph.

Revision ID: 0005_add_entity_graph_tables
Revises: 0004_add_sources_file_mtime
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_add_entity_graph_tables"
down_revision: str | None = "0004_add_sources_file_mtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint("normalized_name", "entity_type", name="uq_entities_name_type"),
    )
    op.create_index("ix_entities_normalized_name", "entities", ["normalized_name"])

    op.create_table(
        "chunk_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("chunks.id"), nullable=False),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("mention_text", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("chunk_id", "entity_id", name="uq_chunk_entities"),
    )
    op.create_index("ix_chunk_entities_chunk_id", "chunk_entities", ["chunk_id"])
    op.create_index("ix_chunk_entities_entity_id", "chunk_entities", ["entity_id"])

    op.create_table(
        "entity_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False
        ),
        sa.Column(
            "target_entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False
        ),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "source_chunk_id", sa.String(length=36), sa.ForeignKey("chunks.id"), nullable=False
        ),
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
        sa.CheckConstraint(
            "source_entity_id != target_entity_id", name="ck_entity_relations_distinct"
        ),
        sa.UniqueConstraint(
            "source_entity_id", "target_entity_id", "relation_type", name="uq_entity_relations"
        ),
    )
    op.create_index("ix_entity_relations_source_entity_id", "entity_relations", ["source_entity_id"])
    op.create_index("ix_entity_relations_target_entity_id", "entity_relations", ["target_entity_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_relations_target_entity_id", table_name="entity_relations")
    op.drop_index("ix_entity_relations_source_entity_id", table_name="entity_relations")
    op.drop_table("entity_relations")

    op.drop_index("ix_chunk_entities_entity_id", table_name="chunk_entities")
    op.drop_index("ix_chunk_entities_chunk_id", table_name="chunk_entities")
    op.drop_table("chunk_entities")

    op.drop_index("ix_entities_normalized_name", table_name="entities")
    op.drop_table("entities")
