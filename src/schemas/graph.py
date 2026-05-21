from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GraphNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    source_type: str
    source_title: str | None = None
    source_path: str | None = None
    chunk_index: int
    label: str
    snippet: str
    token_count: int
    created_at: datetime


class GraphEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    target: str
    similarity: float
    created_at: datetime


class SourceSummary(BaseModel):
    id: str
    source_type: str
    title: str | None
    path: str | None
    created_at: datetime
    chunk_count: int


class TopConnection(BaseModel):
    from_id: str
    to_id: str
    from_label: str
    to_label: str
    similarity: float


class GrowthPoint(BaseModel):
    day: str
    value: int


class DashboardStatsResponse(BaseModel):
    total_chunks: int
    total_edges: int
    total_sources: int
    chunks_today: int
    edges_today: int
    sources_today: int
    source_type_counts: dict[str, int]
    growth_30d: list[GrowthPoint]
    top_connections: list[TopConnection]
    recent_sources: list[SourceSummary]
