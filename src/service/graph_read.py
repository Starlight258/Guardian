from __future__ import annotations

from sqlalchemy.orm import Session

from src.crud.graph import get_dashboard_stats, list_all_edges, list_chunks_with_sources
from src.models import GraphEdge


def get_graph_nodes(session: Session) -> list:
    return list_chunks_with_sources(session)


def get_graph_edges(session: Session) -> list[GraphEdge]:
    return list_all_edges(session)


def get_stats(session: Session) -> dict:
    return get_dashboard_stats(session)
