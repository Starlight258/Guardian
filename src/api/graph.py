from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.deps import get_db
from src.schemas.graph import GraphEdgeResponse, GraphNodeResponse
from src.service.graph_read import get_graph_edges, get_graph_nodes

router = APIRouter(prefix="/graph", tags=["graph"])
DBSession = Depends(get_db)


def _node_label(*, source_title: str | None, source_path: str | None, chunk_id: str) -> str:
    if source_title:
        return source_title
    if source_path:
        return Path(source_path).stem
    return chunk_id[:8]


def _node_snippet(text: str, *, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


@router.get("/nodes", response_model=list[GraphNodeResponse])
def list_graph_nodes(db: Session = DBSession) -> list[GraphNodeResponse]:
    rows = get_graph_nodes(db)
    return [
        GraphNodeResponse(
            id=row["chunk_id"],
            source_id=row["source_id"],
            source_type=row["source_type"],
            source_title=row["title"],
            source_path=row["path"],
            chunk_index=row["chunk_index"],
            label=_node_label(
                source_title=row["title"],
                source_path=row["path"],
                chunk_id=row["chunk_id"],
            ),
            snippet=_node_snippet(row["text"]),
            token_count=row["token_count"],
            created_at=row["chunk_created_at"],
        )
        for row in rows
    ]


@router.get("/edges", response_model=list[GraphEdgeResponse])
def list_graph_edges(db: Session = DBSession) -> list[GraphEdgeResponse]:
    return [
        GraphEdgeResponse(
            source=edge.from_chunk_id,
            target=edge.to_chunk_id,
            similarity=edge.similarity,
            created_at=edge.created_at,
        )
        for edge in get_graph_edges(db)
    ]
