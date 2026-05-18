from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from src.models import Chunk, GraphEdge


def replace_source_chunks(
    session: Session,
    *,
    source_id: str,
    chunks: list[Chunk],
) -> None:
    delete_source_chunks(session, source_id=source_id)
    session.add_all(chunks)


def delete_source_chunks(session: Session, *, source_id: str) -> None:
    chunk_ids = list(session.scalars(select(Chunk.id).where(Chunk.source_id == source_id)))
    if not chunk_ids:
        return

    session.execute(
        delete(GraphEdge).where(
            or_(
                GraphEdge.from_chunk_id.in_(chunk_ids),
                GraphEdge.to_chunk_id.in_(chunk_ids),
            )
        )
    )
    session.execute(delete(Chunk).where(Chunk.source_id == source_id))
