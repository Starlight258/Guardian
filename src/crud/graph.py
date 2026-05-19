from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Chunk, GraphEdge, Source


def list_chunks_with_sources(session: Session) -> list:
    return list(
        session.execute(
            select(
                Chunk.id.label("chunk_id"),
                Chunk.source_id.label("source_id"),
                Chunk.chunk_index,
                Chunk.text,
                Chunk.token_count,
                Chunk.created_at.label("chunk_created_at"),
                Source.source_type,
                Source.title,
                Source.path,
            )
            .join(Source, Chunk.source_id == Source.id)
            .order_by(Chunk.chunk_index, Chunk.created_at)
        )
        .mappings()
        .all()
    )


def list_all_edges(session: Session) -> list[GraphEdge]:
    return list(session.scalars(select(GraphEdge).order_by(GraphEdge.created_at)))
