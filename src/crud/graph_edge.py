from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import GraphEdge


def list_graph_edges(session: Session) -> list[GraphEdge]:
    return list(session.scalars(select(GraphEdge)))


def upsert_graph_edge(
    session: Session,
    *,
    from_chunk_id: str,
    to_chunk_id: str,
    similarity: float,
) -> GraphEdge:
    from_id, to_id = sorted((from_chunk_id, to_chunk_id))
    edge = session.scalar(
        select(GraphEdge).where(
            GraphEdge.from_chunk_id == from_id,
            GraphEdge.to_chunk_id == to_id,
        )
    )
    if edge is None:
        edge = GraphEdge(
            from_chunk_id=from_id,
            to_chunk_id=to_id,
            similarity=similarity,
        )
        session.add(edge)
    else:
        edge.similarity = similarity
    return edge
