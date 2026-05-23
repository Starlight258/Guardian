# ORM 모델: Source, Chunk, GraphEdge, RecallLog.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.db import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    path: Mapped[str | None] = mapped_column(String(1024), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    file_mtime: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("source_id", "chunk_index", name="uq_chunks_source_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="chunks")


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        CheckConstraint("from_chunk_id != to_chunk_id", name="ck_graph_edges_distinct_chunks"),
        UniqueConstraint("from_chunk_id", "to_chunk_id", name="uq_graph_edges_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), index=True)
    to_chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), index=True)
    similarity: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecallLog(Base):
    __tablename__ = "recall_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    angel_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    drop_reason: Mapped[str | None] = mapped_column(String(64))
    angel_message: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
