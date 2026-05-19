from __future__ import annotations

import math
import sys
import types
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import Base
from src.models import Chunk, GraphEdge, Source
from src.service.embed import (
    ChromaChunkVectorStore,
    SentenceTransformerEmbedder,
    VectorSearchResult,
)
from src.service.graph import GraphService
from src.service.note_ingest import ingest_obsidian_note


def make_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def make_unmigrated_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        if "unrelated" in text:
            return [0.0, 1.0]
        return [1.0, 0.0]


class FakeVectorStore:
    def __init__(self) -> None:
        self.embeddings: dict[str, list[float]] = {}
        self.deleted_ids: list[str] = []

    def upsert_chunk(self, chunk: Chunk, embedding: list[float]) -> None:
        self.embeddings[chunk.id] = embedding

    def query_similar(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        results = [
            VectorSearchResult(chunk_id=chunk_id, similarity=_cosine(embedding, existing))
            for chunk_id, existing in self.embeddings.items()
        ]
        return sorted(results, key=lambda result: result.similarity, reverse=True)[:limit]

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        self.deleted_ids.extend(chunk_ids)
        for chunk_id in chunk_ids:
            self.embeddings.pop(chunk_id, None)


def test_connect_chunks_stores_vectors_and_edges_for_similar_candidates(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    vector_store = FakeVectorStore()
    graph_service = GraphService(
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        similarity_threshold=0.75,
        top_k=5,
    )
    first_note = tmp_path / "first.md"
    second_note = tmp_path / "second.md"
    first_note.write_text("alpha beta gamma", encoding="utf-8")
    second_note.write_text("alpha beta delta", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=first_note, graph_service=graph_service)
        ingest_obsidian_note(session, path=second_note, graph_service=graph_service)

    with session_factory() as session:
        chunks = list(session.scalars(select(Chunk)))
        edges = list(session.scalars(select(GraphEdge)))

    assert len(chunks) == 2
    assert set(vector_store.embeddings) == {chunk.id for chunk in chunks}
    assert len(edges) == 1
    assert edges[0].similarity == 1.0
    assert graph_service.graph.has_edge(edges[0].from_chunk_id, edges[0].to_chunk_id)


def test_connect_chunks_skips_candidates_below_similarity_threshold(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    graph_service = GraphService(
        embedder=FakeEmbedder(),
        vector_store=FakeVectorStore(),
        similarity_threshold=0.75,
        top_k=5,
    )
    first_note = tmp_path / "first.md"
    second_note = tmp_path / "second.md"
    first_note.write_text("alpha beta gamma", encoding="utf-8")
    second_note.write_text("unrelated context", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=first_note, graph_service=graph_service)
        ingest_obsidian_note(session, path=second_note, graph_service=graph_service)

    with session_factory() as session:
        edges = list(session.scalars(select(GraphEdge)))

    assert edges == []


def test_reconstruct_loads_sqlite_edges_into_networkx() -> None:
    session_factory = make_session_factory()
    graph_service = GraphService(
        embedder=FakeEmbedder(),
        vector_store=FakeVectorStore(),
    )

    with session_factory() as session:
        source = Source(
            id=str(uuid4()),
            source_type="obsidian_note",
            title="note",
            path="/tmp/note.md",
            metadata_json={},
            content_hash="source-hash",
        )
        first = _chunk(source.id, "first", chunk_index=0)
        second = _chunk(source.id, "second", chunk_index=1)
        session.add_all([source, first, second])
        session.flush()
        session.add(GraphEdge(from_chunk_id=first.id, to_chunk_id=second.id, similarity=0.9))
        session.commit()

    with session_factory() as session:
        graph_service.reconstruct(session)

    assert graph_service.graph.has_node(first.id)
    assert graph_service.graph.has_edge(first.id, second.id)
    assert graph_service.graph.edges[first.id, second.id]["similarity"] == 0.9


def test_reconstruct_tolerates_missing_tables_on_fresh_database() -> None:
    session_factory = make_unmigrated_session_factory()
    graph_service = GraphService(
        embedder=FakeEmbedder(),
        vector_store=FakeVectorStore(),
    )

    with session_factory() as session:
        graph_service.reconstruct(session)

    assert graph_service.graph.number_of_nodes() == 0
    assert graph_service.graph.number_of_edges() == 0


def test_ingest_rolls_back_new_vectors_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_factory = make_session_factory()
    vector_store = FakeVectorStore()
    graph_service = GraphService(
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        similarity_threshold=0.75,
        top_k=5,
    )
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path, graph_service=graph_service)

    with session_factory() as session:
        old_chunk = session.scalar(select(Chunk))
        assert old_chunk is not None
        old_chunk_id = old_chunk.id

    note_path.write_text("alpha beta delta", encoding="utf-8")
    with session_factory() as session:
        monkeypatch.setattr(
            session,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("commit failed")),
        )
        with pytest.raises(RuntimeError, match="commit failed"):
            ingest_obsidian_note(session, path=note_path, graph_service=graph_service)

    with session_factory() as session:
        chunks = list(session.scalars(select(Chunk)))

    assert [chunk.id for chunk in chunks] == [old_chunk_id]
    assert set(vector_store.embeddings) == {old_chunk_id}
    assert graph_service.graph.has_node(old_chunk_id)


def test_chroma_vector_store_persists_chunk_vectors(tmp_path: Path) -> None:
    vector_store = ChromaChunkVectorStore(path=tmp_path / "chroma")
    chunk = _chunk("source-1", "alpha beta")

    vector_store.upsert_chunk(chunk, [1.0, 0.0])
    results = vector_store.query_similar([1.0, 0.0], limit=5)

    assert results[0].chunk_id == chunk.id
    assert results[0].similarity >= 0.99


def test_sentence_transformer_embedder_uses_bge_m3_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}

    class FakeModel:
        def __init__(self, model_name: str) -> None:
            calls["model_name"] = model_name

        def encode(self, texts: list[str], *, normalize_embeddings: bool):
            calls["texts"] = texts
            calls["normalize_embeddings"] = normalize_embeddings
            return [FakeEmbedding([0.1, 0.2])]

    class FakeEmbedding(list):
        def tolist(self) -> list[float]:
            return list(self)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeModel),
    )

    embedding = SentenceTransformerEmbedder().embed("alpha beta")

    assert embedding == [0.1, 0.2]
    assert calls == {
        "model_name": "BAAI/bge-m3",
        "texts": ["alpha beta"],
        "normalize_embeddings": True,
    }


def test_chroma_vector_store_uses_guardian_chunks_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = {}

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            calls["path"] = path

        def get_or_create_collection(self, *, name: str, metadata: dict[str, str]):
            calls["name"] = name
            calls["metadata"] = metadata
            return object()

    monkeypatch.setitem(
        sys.modules,
        "chromadb",
        types.SimpleNamespace(PersistentClient=FakeClient),
    )

    ChromaChunkVectorStore(path=tmp_path / "chroma")

    assert calls == {
        "path": str(tmp_path / "chroma"),
        "name": "guardian_chunks",
        "metadata": {"hnsw:space": "cosine"},
    }


def _chunk(source_id: str, text: str, chunk_index: int = 0) -> Chunk:
    return Chunk(
        id=str(uuid4()),
        source_id=source_id,
        chunk_index=chunk_index,
        text=text,
        token_count=len(text.split()),
        content_hash=text,
    )


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm)
