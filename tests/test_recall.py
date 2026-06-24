from __future__ import annotations

from collections.abc import Callable

import networkx as nx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.main as main
from src.db import Base
from src.deps import get_db
from src.models import Chunk, RecallLog, Source
from src.service.embed import VectorSearchResult
from src.service.recall import RecallAgent, RecallContext


def make_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0] if "context" in text else [0.0, 1.0]


class FakeVectorStore:
    def __init__(self) -> None:
        self.embeddings: dict[str, list[float]] = {}
        self.query_results: list[VectorSearchResult] = []
        self.last_where: dict | None = None

    def upsert_chunk(self, chunk: Chunk, embedding: list[float]) -> None:
        self.embeddings[chunk.id] = embedding

    def query_similar(
        self, embedding: list[float], *, limit: int, where: dict | None = None
    ) -> list[VectorSearchResult]:
        del embedding
        self.last_where = where
        return self.query_results[:limit]

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            self.embeddings.pop(chunk_id, None)


class FakeReranker:
    """원래 벡터 검색 순서를 그대로 보존하는 reranker — 실제 cross-encoder 모델 로드를 피한다."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        del query
        return [float(len(documents) - index) for index in range(len(documents))]


class FakeGraphService:
    def __init__(self) -> None:
        self.embedder = FakeEmbedder()
        self.vector_store = FakeVectorStore()
        self.graph = nx.Graph()

    def reconstruct(self, session: Session) -> None:
        del session


class FakeLLMClient:
    def __init__(
        self,
        *,
        chunk_ids: list[str],
        evidence_sources: list[str],
        relevance_score: float,
        angel_message: str,
    ) -> None:
        self.chunk_ids = chunk_ids
        self.evidence_sources = evidence_sources
        self.relevance_score = relevance_score
        self.angel_message = angel_message
        self.prompts: list[str] = []
        self.evidence_payloads: list[list[str]] = []

    def complete(self, *, prompt: str, evidence, tool_schema):  # type: ignore[no-untyped-def]
        del tool_schema
        self.prompts.append(prompt)
        self.evidence_payloads.append([item.chunk_id for item in evidence])
        return {
            "content": [
                {
                    "type": "tool_use",
                    "name": "angel_output",
                    "input": {
                        "chunk_ids": self.chunk_ids,
                        "evidence_sources": self.evidence_sources,
                        "relevance_score": self.relevance_score,
                        "angel_message": self.angel_message,
                    },
                }
            ]
        }


def _seed_chunk(
    session: Session,
    *,
    source_id: str,
    chunk_index: int,
    text: str,
    title: str,
    path: str,
) -> Chunk:
    source = session.get(Source, source_id)
    if source is None:
        source = Source(
            id=source_id,
            source_type="obsidian_note",
            title=title,
            path=path,
            metadata_json={},
            content_hash=f"{source_id}-hash",
        )
        session.add(source)
    chunk = Chunk(
        id=f"{source_id}-chunk-{chunk_index}",
        source_id=source_id,
        chunk_index=chunk_index,
        text=text,
        token_count=len(text.split()),
        content_hash=f"{source_id}-chunk-{chunk_index}-hash",
    )
    session.add(chunk)
    session.flush()
    return chunk


def test_recall_endpoint_persists_triggered_angel_message(monkeypatch) -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()

    with session_factory() as session:
        first = _seed_chunk(
            session,
            source_id="source-1",
            chunk_index=0,
            text="context alpha beta",
            title="Alpha Note",
            path="/tmp/alpha.md",
        )
        second = _seed_chunk(
            session,
            source_id="source-2",
            chunk_index=0,
            text="neighbor gamma delta",
            title="Beta Note",
            path="/tmp/beta.md",
        )
        session.add(
            Source(
                id="source-3",
                source_type="obsidian_note",
                title="Unused",
                path="/tmp/unused.md",
                metadata_json={},
                content_hash="source-3-hash",
            )
        )
        session.commit()

    graph_service.graph.add_node(first.id, source_id=first.source_id)
    graph_service.graph.add_node(second.id, source_id=second.source_id)
    graph_service.graph.add_edge(first.id, second.id, similarity=0.88)
    graph_service.vector_store.query_results = [
        VectorSearchResult(chunk_id=first.id, similarity=0.93)
    ]

    long_message = "x" * 121
    llm_client = FakeLLMClient(
        chunk_ids=[first.id, second.id],
        evidence_sources=["source-1", "source-2"],
        relevance_score=0.82,
        angel_message=long_message,
    )
    agent = RecallAgent(graph_service=graph_service, llm_client=llm_client, reranker=FakeReranker())

    def override_get_db():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(main, "GraphService", lambda: graph_service)
    monkeypatch.setattr(main, "RecallAgent", lambda **kwargs: agent)
    main.app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/recall",
                json={
                    "context": "context about alpha and beta",
                    "session_id": "session-1",
                    "cwd": "/tmp/guardian",
                    "metadata": {"source": "manual"},
                },
            )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["angel_triggered"] is True
    assert payload["drop_reason"] is None
    assert payload["relevance_score"] == 0.82
    assert payload["angel_message"] == long_message[:120]
    assert payload["retrieved_chunk_ids"] == [first.id, second.id]
    assert payload["evidence_source_ids"] == ["source-1", "source-2"]
    assert len(payload["angel_message"]) == 120

    with session_factory() as session:
        log = session.scalar(select(RecallLog))

    assert log is not None
    assert log.input_hash == payload["input_hash"]
    assert log.retrieved_chunk_ids == [first.id, second.id]
    assert log.evidence_source_ids == ["source-1", "source-2"]
    assert log.angel_triggered is True
    assert log.drop_reason is None
    assert log.angel_message == long_message[:120]


def test_recall_endpoint_drops_below_threshold(monkeypatch) -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()

    with session_factory() as session:
        first = _seed_chunk(
            session,
            source_id="source-1",
            chunk_index=0,
            text="context alpha beta",
            title="Alpha Note",
            path="/tmp/alpha.md",
        )
        session.commit()

    graph_service.graph.add_node(first.id, source_id=first.source_id)
    graph_service.vector_store.query_results = [
        VectorSearchResult(chunk_id=first.id, similarity=0.8)
    ]

    llm_client = FakeLLMClient(
        chunk_ids=[first.id],
        evidence_sources=["source-1"],
        relevance_score=0.3,
        angel_message="this should be dropped",
    )
    agent = RecallAgent(graph_service=graph_service, llm_client=llm_client, reranker=FakeReranker())

    def override_get_db():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(main, "GraphService", lambda: graph_service)
    monkeypatch.setattr(main, "RecallAgent", lambda **kwargs: agent)
    main.app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(main.app) as client:
            response = client.post("/recall", json={"context": "context alpha beta"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dropped"
    assert payload["angel_triggered"] is False
    assert payload["drop_reason"] == "below_threshold"
    assert payload["angel_message"] is None

    with session_factory() as session:
        log = session.scalar(select(RecallLog))

    assert log is not None
    assert log.angel_triggered is False
    assert log.drop_reason == "below_threshold"
    assert log.angel_message is None


def test_recall_endpoint_handles_empty_chunk_ids(monkeypatch) -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()

    with session_factory() as session:
        first = _seed_chunk(
            session,
            source_id="source-1",
            chunk_index=0,
            text="context alpha beta",
            title="Alpha Note",
            path="/tmp/alpha.md",
        )
        session.commit()

    graph_service.vector_store.query_results = [
        VectorSearchResult(chunk_id=first.id, similarity=0.9)
    ]
    llm_client = FakeLLMClient(
        chunk_ids=[],
        evidence_sources=["source-1"],
        relevance_score=0.9,
        angel_message="ignored",
    )
    agent = RecallAgent(graph_service=graph_service, llm_client=llm_client, reranker=FakeReranker())

    def override_get_db():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(main, "GraphService", lambda: graph_service)
    monkeypatch.setattr(main, "RecallAgent", lambda **kwargs: agent)
    main.app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(main.app) as client:
            response = client.post("/recall", json={"context": "context alpha beta"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dropped"
    assert payload["drop_reason"] == "empty_chunk_ids"
    assert payload["angel_triggered"] is False


class _ReversingReranker:
    """벡터 검색 순서를 뒤집어서, reranker가 실제로 순서를 바꾸는지 검증한다."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        del query
        return [float(index) for index in range(len(documents))]


def test_retrieve_evidence_reorders_pool_by_rerank_score() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()

    with session_factory() as session:
        first = _seed_chunk(
            session,
            source_id="source-1",
            chunk_index=0,
            text="context alpha beta",
            title="Alpha Note",
            path="/tmp/alpha.md",
        )
        second = _seed_chunk(
            session,
            source_id="source-2",
            chunk_index=0,
            text="context gamma delta",
            title="Beta Note",
            path="/tmp/beta.md",
        )
        session.commit()

    # 코사인 유사도 기준으로는 first가 1위지만, reranker가 순서를 뒤집는다.
    graph_service.vector_store.query_results = [
        VectorSearchResult(chunk_id=first.id, similarity=0.95),
        VectorSearchResult(chunk_id=second.id, similarity=0.80),
    ]

    agent = RecallAgent(graph_service=graph_service, reranker=_ReversingReranker())
    context = RecallContext(text="context about alpha and gamma")

    with session_factory() as session:
        evidence = agent._retrieve_evidence(session, context)

    assert [item.chunk_id for item in evidence] == [second.id, first.id]


def test_retrieve_evidence_passes_source_type_filter_to_vector_search() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()
    agent = RecallAgent(graph_service=graph_service, reranker=FakeReranker())
    context = RecallContext(
        text="check obsidian notes only",
        metadata={"source_type": "obsidian_note"},
    )

    with session_factory() as session:
        agent._retrieve_evidence(session, context)

    assert graph_service.vector_store.last_where == {"source_type": "obsidian_note"}


def test_retrieve_evidence_skips_filter_when_source_type_not_set() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()
    agent = RecallAgent(graph_service=graph_service, reranker=FakeReranker())
    context = RecallContext(text="no filter here")

    with session_factory() as session:
        agent._retrieve_evidence(session, context)

    assert graph_service.vector_store.last_where is None


def test_retrieve_evidence_expands_via_entity_graph() -> None:
    from src.crud.entity import record_chunk_entity
    from src.service.entity_graph import EntityGraphService

    session_factory = make_session_factory()
    graph_service = FakeGraphService()

    with session_factory() as session:
        matched = _seed_chunk(
            session,
            source_id="source-1",
            chunk_index=0,
            text="context about RAG",
            title="RAG Note",
            path="/tmp/rag.md",
        )
        unmatched = _seed_chunk(
            session,
            source_id="source-2",
            chunk_index=0,
            text="completely different wording about embeddings",
            title="Embeddings Note",
            path="/tmp/embeddings.md",
        )
        record_chunk_entity(
            session, chunk_id=matched.id, entity_id="entity-rag", mention_text="RAG"
        )
        record_chunk_entity(
            session, chunk_id=unmatched.id, entity_id="entity-embed", mention_text="embeddings"
        )
        session.commit()

    graph_service.vector_store.query_results = [
        VectorSearchResult(chunk_id=matched.id, similarity=0.95)
    ]

    entity_graph_service = EntityGraphService(extractor=object())
    entity_graph_service.graph.add_edge("entity-rag", "entity-embed")

    agent = RecallAgent(
        graph_service=graph_service,
        reranker=FakeReranker(),
        entity_graph_service=entity_graph_service,
    )
    context = RecallContext(text="context about RAG")

    with session_factory() as session:
        evidence = agent._retrieve_evidence(session, context)

    assert {item.chunk_id for item in evidence} == {matched.id, unmatched.id}
    entity_evidence = next(item for item in evidence if item.chunk_id == unmatched.id)
    assert entity_evidence.relation == "entity"
    assert entity_evidence.neighbor_of == matched.id

