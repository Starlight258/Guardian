from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.crud.entity import get_or_create_entity, upsert_entity_relation
from src.db import Base
from src.models import Chunk, CommunitySummary, Entity, Source
from src.service.community_summarize import recompute_communities
from src.service.entity_extract import ExtractionResult
from src.service.entity_graph import EntityGraphService


def make_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class FakeExtractor:
    def extract(self, text: str) -> ExtractionResult:
        return ExtractionResult()


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], list[str]]] = []

    def summarize(self, *, entities: list[str], relations: list[str]) -> str:
        self.calls.append((entities, relations))
        return f"커뮤니티: {', '.join(sorted(entities))}"


def _seed_chunk(session: Session) -> Chunk:
    source = Source(
        id="source-1",
        source_type="obsidian_note",
        title="Note",
        path="/tmp/note.md",
        metadata_json={},
        content_hash="hash",
    )
    session.add(source)
    chunk = Chunk(
        id="chunk-1",
        source_id="source-1",
        chunk_index=0,
        text="text",
        token_count=1,
        content_hash="chunk-1-hash",
    )
    session.add(chunk)
    session.flush()
    return chunk


def test_recompute_communities_summarizes_and_assigns_community_id() -> None:
    session_factory = make_session_factory()
    service = EntityGraphService(extractor=FakeExtractor())
    summarizer = FakeSummarizer()

    with session_factory() as session:
        chunk = _seed_chunk(session)
        a = get_or_create_entity(session, name="A", entity_type="CONCEPT")
        b = get_or_create_entity(session, name="B", entity_type="CONCEPT")
        upsert_entity_relation(
            session,
            source_entity_id=a.id,
            target_entity_id=b.id,
            relation_type="uses",
            description="A uses B",
            source_chunk_id=chunk.id,
        )
        session.commit()
        service.reconstruct(session)

        created = recompute_communities(
            session, entity_graph_service=service, summarizer=summarizer
        )
        session.commit()

    assert len(created) == 1
    assert summarizer.calls == [(["A", "B"], ["A -[uses]-> B: A uses B"])]

    with session_factory() as session:
        summaries = list(session.scalars(select(CommunitySummary)))
        entities = list(session.scalars(select(Entity)))

    assert len(summaries) == 1
    assert summaries[0].entity_count == 2
    assert all(entity.community_id == summaries[0].id for entity in entities)


def test_recompute_communities_skips_singleton_communities() -> None:
    session_factory = make_session_factory()
    service = EntityGraphService(extractor=FakeExtractor())
    summarizer = FakeSummarizer()

    with session_factory() as session:
        get_or_create_entity(session, name="Lonely", entity_type="CONCEPT")
        session.commit()
        service.reconstruct(session)

        created = recompute_communities(
            session, entity_graph_service=service, summarizer=summarizer
        )
        session.commit()

    assert created == []
    assert summarizer.calls == []

    with session_factory() as session:
        assert list(session.scalars(select(CommunitySummary))) == []


def test_recompute_communities_replaces_previous_summaries() -> None:
    session_factory = make_session_factory()
    service = EntityGraphService(extractor=FakeExtractor())
    summarizer = FakeSummarizer()

    with session_factory() as session:
        chunk = _seed_chunk(session)
        a = get_or_create_entity(session, name="A", entity_type="CONCEPT")
        b = get_or_create_entity(session, name="B", entity_type="CONCEPT")
        upsert_entity_relation(
            session,
            source_entity_id=a.id,
            target_entity_id=b.id,
            relation_type="uses",
            description="A uses B",
            source_chunk_id=chunk.id,
        )
        session.commit()
        service.reconstruct(session)
        recompute_communities(session, entity_graph_service=service, summarizer=summarizer)
        session.commit()

    with session_factory() as session:
        first_summary_id = session.scalar(select(CommunitySummary)).id

        c = get_or_create_entity(session, name="C", entity_type="CONCEPT")
        d = get_or_create_entity(session, name="D", entity_type="CONCEPT")
        chunk = session.get(Chunk, "chunk-1")
        upsert_entity_relation(
            session,
            source_entity_id=c.id,
            target_entity_id=d.id,
            relation_type="uses",
            description="C uses D",
            source_chunk_id=chunk.id,
        )
        session.commit()
        service.reconstruct(session)
        recompute_communities(session, entity_graph_service=service, summarizer=summarizer)
        session.commit()

    with session_factory() as session:
        summaries = list(session.scalars(select(CommunitySummary)))

    assert len(summaries) == 2
    assert first_summary_id not in {summary.id for summary in summaries}
