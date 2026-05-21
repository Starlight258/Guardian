from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

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


def get_dashboard_stats(session: Session) -> dict:
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
    thirty_days_ago = today - timedelta(days=29)
    window_start = datetime.combine(thirty_days_ago, datetime.min.time()).replace(tzinfo=UTC)

    total_chunks = session.scalar(select(func.count(Chunk.id))) or 0
    total_edges = session.scalar(select(func.count(GraphEdge.id))) or 0
    total_sources = session.scalar(select(func.count(Source.id))) or 0

    chunks_today = (
        session.scalar(select(func.count(Chunk.id)).where(Chunk.created_at >= today_start)) or 0
    )
    edges_today = (
        session.scalar(
            select(func.count(GraphEdge.id)).where(GraphEdge.created_at >= today_start)
        ) or 0
    )
    sources_today = (
        session.scalar(select(func.count(Source.id)).where(Source.created_at >= today_start)) or 0
    )

    type_rows = session.execute(
        select(Source.source_type, func.count(Source.id).label("cnt")).group_by(Source.source_type)
    ).all()
    source_type_counts = {row.source_type: row.cnt for row in type_rows}

    chunk_dates = session.scalars(
        select(Chunk.created_at).where(Chunk.created_at >= window_start)
    ).all()
    base_count = (
        session.scalar(select(func.count(Chunk.id)).where(Chunk.created_at < window_start)) or 0
    )

    day_counts: dict[date, int] = {}
    for ts in chunk_dates:
        if isinstance(ts, str):
            d = datetime.fromisoformat(ts).date()
        elif hasattr(ts, "date"):
            d = ts.date()
        else:
            d = ts
        day_counts[d] = day_counts.get(d, 0) + 1

    cumulative = base_count
    growth_30d = []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        cumulative += day_counts.get(d, 0)
        growth_30d.append({"day": d.isoformat(), "value": cumulative})

    from_c = aliased(Chunk)
    to_c = aliased(Chunk)
    from_s = aliased(Source)
    to_s = aliased(Source)

    top_edges = session.execute(
        select(
            GraphEdge.from_chunk_id,
            GraphEdge.to_chunk_id,
            GraphEdge.similarity,
            from_s.title.label("from_title"),
            from_s.path.label("from_path"),
            to_s.title.label("to_title"),
            to_s.path.label("to_path"),
        )
        .join(from_c, from_c.id == GraphEdge.from_chunk_id)
        .join(from_s, from_s.id == from_c.source_id)
        .join(to_c, to_c.id == GraphEdge.to_chunk_id)
        .join(to_s, to_s.id == to_c.source_id)
        .order_by(GraphEdge.similarity.desc())
        .limit(5)
    ).all()

    def _lbl(title: str | None, path: str | None, fallback: str) -> str:
        if title:
            return title
        if path:
            return Path(path).stem
        return fallback

    top_connections = [
        {
            "from_id": row.from_chunk_id,
            "to_id": row.to_chunk_id,
            "from_label": _lbl(row.from_title, row.from_path, row.from_chunk_id[:8]),
            "to_label": _lbl(row.to_title, row.to_path, row.to_chunk_id[:8]),
            "similarity": row.similarity,
        }
        for row in top_edges
    ]

    recent_rows = session.execute(
        select(Source, func.count(Chunk.id).label("chunk_count"))
        .outerjoin(Chunk, Chunk.source_id == Source.id)
        .group_by(Source.id)
        .order_by(Source.created_at.desc())
        .limit(20)
    ).all()

    recent_sources = [
        {
            "id": src.id,
            "source_type": src.source_type,
            "title": src.title,
            "path": src.path,
            "created_at": src.created_at,
            "chunk_count": chunk_count,
        }
        for src, chunk_count in recent_rows
    ]

    return {
        "total_chunks": total_chunks,
        "total_edges": total_edges,
        "total_sources": total_sources,
        "chunks_today": chunks_today,
        "edges_today": edges_today,
        "sources_today": sources_today,
        "source_type_counts": source_type_counts,
        "growth_30d": growth_30d,
        "top_connections": top_connections,
        "recent_sources": recent_sources,
    }
