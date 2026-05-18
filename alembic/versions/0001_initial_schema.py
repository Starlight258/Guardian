"""Initial Guardian schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("path", sa.String(length=1024), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
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
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_index("ix_sources_path", "sources", ["path"])
    op.create_index("ix_sources_commit_sha", "sources", ["commit_sha"], unique=True)

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source_id", "chunk_index", name="uq_chunks_source_index"),
    )
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])

    op.create_table(
        "graph_edges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "from_chunk_id",
            sa.String(length=36),
            sa.ForeignKey("chunks.id"),
            nullable=False,
        ),
        sa.Column("to_chunk_id", sa.String(length=36), sa.ForeignKey("chunks.id"), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("from_chunk_id != to_chunk_id", name="ck_graph_edges_distinct_chunks"),
        sa.UniqueConstraint("from_chunk_id", "to_chunk_id", name="uq_graph_edges_pair"),
    )
    op.create_index("ix_graph_edges_from_chunk_id", "graph_edges", ["from_chunk_id"])
    op.create_index("ix_graph_edges_to_chunk_id", "graph_edges", ["to_chunk_id"])

    op.create_table(
        "recall_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("evidence_source_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("angel_triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("drop_reason", sa.String(length=64), nullable=True),
        sa.Column("angel_message", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_recall_logs_input_hash", "recall_logs", ["input_hash"])
    op.create_index("ix_recall_logs_created_at", "recall_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_recall_logs_created_at", table_name="recall_logs")
    op.drop_index("ix_recall_logs_input_hash", table_name="recall_logs")
    op.drop_table("recall_logs")

    op.drop_index("ix_graph_edges_to_chunk_id", table_name="graph_edges")
    op.drop_index("ix_graph_edges_from_chunk_id", table_name="graph_edges")
    op.drop_table("graph_edges")

    op.drop_index("ix_chunks_source_id", table_name="chunks")
    op.drop_table("chunks")

    op.drop_index("ix_sources_commit_sha", table_name="sources")
    op.drop_index("ix_sources_path", table_name="sources")
    op.drop_index("ix_sources_source_type", table_name="sources")
    op.drop_table("sources")
