# 그래프 라우터: 대시보드용 /nodes, /edges, /stats 엔드포인트.
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.deps import get_db
from src.schemas.graph import (
    DashboardStatsResponse,
    GraphEdgeResponse,
    GraphNodeResponse,
    GrowthPoint,
    SourceSummary,
    TopConnection,
)
from src.service.graph_read import get_graph_edges, get_graph_nodes, get_stats

router = APIRouter(prefix="/graph", tags=["graph"])
DBSession = Depends(get_db)


def _node_label(*, source_title: str | None, source_path: str | None, chunk_id: str) -> str:
    # 우선순위: title > path stem > chunk_id 앞 8자.
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


@router.get("/stats", response_model=DashboardStatsResponse)
def dashboard_stats(db: Session = DBSession) -> DashboardStatsResponse:
    raw = get_stats(db)
    return DashboardStatsResponse(
        total_chunks=raw["total_chunks"],
        total_edges=raw["total_edges"],
        total_sources=raw["total_sources"],
        chunks_today=raw["chunks_today"],
        edges_today=raw["edges_today"],
        sources_today=raw["sources_today"],
        source_type_counts=raw["source_type_counts"],
        growth_30d=[GrowthPoint(**p) for p in raw["growth_30d"]],
        top_connections=[TopConnection(**c) for c in raw["top_connections"]],
        recent_sources=[SourceSummary(**s) for s in raw["recent_sources"]],
    )
