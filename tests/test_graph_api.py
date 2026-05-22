from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db as db_module
import src.main as main
from src.db import Base
from src.models import Chunk, GraphEdge, Source


class FakeGraphService:
    def reconstruct(self, session) -> None:
        return None


def make_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _seed_graph(session: Session) -> tuple[Chunk, Chunk, GraphEdge]:
    source = Source(
        id=str(uuid4()),
        source_type="obsidian_note",
        title="Graph note",
        path="/tmp/graph-note.md",
        metadata_json={},
        content_hash="source-hash",
    )
    first = Chunk(
        id=str(uuid4()),
        source_id=source.id,
        chunk_index=0,
        text="alpha beta gamma",
        token_count=3,
        content_hash="chunk-hash-1",
        created_at=datetime.now(UTC),
    )
    second = Chunk(
        id=str(uuid4()),
        source_id=source.id,
        chunk_index=1,
        text="delta epsilon zeta",
        token_count=3,
        content_hash="chunk-hash-2",
        created_at=datetime.now(UTC),
    )
    edge = GraphEdge(
        from_chunk_id=first.id,
        to_chunk_id=second.id,
        similarity=0.91,
        created_at=datetime.now(UTC),
    )
    session.add_all([source, first, second, edge])
    session.commit()
    return first, second, edge


def test_graph_endpoints_return_nodes_and_edges(monkeypatch) -> None:
    session_factory = make_session_factory()
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    monkeypatch.setattr(main, "GraphService", FakeGraphService)
    monkeypatch.setattr(main, "create_watchers_from_env", lambda **kwargs: [])

    with session_factory() as session:
        first, second, edge = _seed_graph(session)

    with TestClient(main.app) as client:
        nodes_response = client.get("/graph/nodes")
        edges_response = client.get("/graph/edges")

    assert nodes_response.status_code == 200
    assert edges_response.status_code == 200

    nodes = nodes_response.json()
    edges = edges_response.json()

    assert [node["id"] for node in nodes] == [first.id, second.id]
    assert nodes[0]["label"] == "Graph note"
    assert nodes[0]["snippet"] == "alpha beta gamma"
    assert nodes[0]["source_path"] == "/tmp/graph-note.md"
    assert nodes[1]["chunk_index"] == 1

    assert edges == [
        {
            "source": edge.from_chunk_id,
            "target": edge.to_chunk_id,
            "similarity": edge.similarity,
            "created_at": edge.created_at.replace(tzinfo=None).isoformat(),
        }
    ]
