from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.crud.entity import get_or_create_entity, normalize_entity_name, upsert_entity_relation
from src.db import Base
from src.models import Chunk, ChunkEntity, Entity, EntityRelation, Source
from src.service.entity_extract import ExtractedEntity, ExtractedRelation, ExtractionResult
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
    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def extract(self, text: str) -> ExtractionResult:
        self.calls.append(text)
        return self.result


def _seed_chunk(session: Session, *, chunk_id: str = "chunk-1", text: str = "text") -> Chunk:
    source = session.get(Source, "source-1")
    if source is None:
        source = Source(
            id="source-1",
            source_type="obsidian_note",
            title="Note",
            path="/tmp/note.md",
            metadata_json={},
            content_hash="hash",
        )
        session.add(source)
    chunk_index = session.scalar(select(func.count()).select_from(Chunk)) or 0
    chunk = Chunk(
        id=chunk_id,
        source_id="source-1",
        chunk_index=chunk_index,
        text=text,
        token_count=len(text.split()),
        content_hash=f"{chunk_id}-hash",
    )
    session.add(chunk)
    session.flush()
    return chunk


def test_normalize_entity_name_collapses_case_and_whitespace() -> None:
    assert normalize_entity_name("  BGE-M3  ") == "bge-m3"
    assert normalize_entity_name("BGE-M3") == normalize_entity_name("bge-m3")


def test_get_or_create_entity_dedups_by_normalized_name_and_type() -> None:
    session_factory = make_session_factory()
    with session_factory() as session:
        first = get_or_create_entity(session, name="BGE-M3", entity_type="TECHNOLOGY")
        second = get_or_create_entity(session, name="bge-m3", entity_type="TECHNOLOGY")
        session.commit()

        assert first.id == second.id
        entities = list(session.scalars(select(Entity)))
        assert len(entities) == 1
        assert entities[0].mention_count == 2


def test_get_or_create_entity_treats_different_type_as_distinct() -> None:
    session_factory = make_session_factory()
    with session_factory() as session:
        first = get_or_create_entity(session, name="RAG", entity_type="CONCEPT")
        second = get_or_create_entity(session, name="RAG", entity_type="PROJECT")
        session.commit()

        assert first.id != second.id
        assert len(list(session.scalars(select(Entity)))) == 2


def test_upsert_entity_relation_increments_weight_on_repeat() -> None:
    session_factory = make_session_factory()
    with session_factory() as session:
        chunk = _seed_chunk(session)
        a = get_or_create_entity(session, name="A", entity_type="CONCEPT")
        b = get_or_create_entity(session, name="B", entity_type="CONCEPT")
        session.flush()

        upsert_entity_relation(
            session,
            source_entity_id=a.id,
            target_entity_id=b.id,
            relation_type="uses",
            description="first",
            source_chunk_id=chunk.id,
        )
        upsert_entity_relation(
            session,
            source_entity_id=a.id,
            target_entity_id=b.id,
            relation_type="uses",
            description="second",
            source_chunk_id=chunk.id,
        )
        session.commit()

        relations = list(session.scalars(select(EntityRelation)))
        assert len(relations) == 1
        assert relations[0].weight == 2


def test_entity_graph_service_extract_and_store_persists_and_updates_graph() -> None:
    session_factory = make_session_factory()
    extraction = ExtractionResult(
        entities=[
            ExtractedEntity(name="BGE-M3", entity_type="TECHNOLOGY"),
            ExtractedEntity(name="Chroma", entity_type="TECHNOLOGY"),
        ],
        relations=[
            ExtractedRelation(
                source="BGE-M3",
                target="Chroma",
                relation_type="stores_into",
                description="embeds then stores",
            )
        ],
    )
    service = EntityGraphService(extractor=FakeExtractor(extraction))

    with session_factory() as session:
        chunk = _seed_chunk(session)
        service.extract_and_store(session, chunk)
        session.commit()

    with session_factory() as session:
        entities = list(session.scalars(select(Entity)))
        relations = list(session.scalars(select(EntityRelation)))
        chunk_entities = list(session.scalars(select(ChunkEntity)))

    assert len(entities) == 2
    assert len(relations) == 1
    assert len(chunk_entities) == 2
    assert service.graph.number_of_nodes() == 2
    assert service.graph.number_of_edges() == 1


def test_entity_graph_service_skips_relation_with_unmatched_entity() -> None:
    session_factory = make_session_factory()
    extraction = ExtractionResult(
        entities=[ExtractedEntity(name="A", entity_type="CONCEPT")],
        relations=[
            ExtractedRelation(
                source="A", target="GHOST", relation_type="uses", description="ignored"
            )
        ],
    )
    service = EntityGraphService(extractor=FakeExtractor(extraction))

    with session_factory() as session:
        chunk = _seed_chunk(session)
        service.extract_and_store(session, chunk)
        session.commit()

    with session_factory() as session:
        relations = list(session.scalars(select(EntityRelation)))

    assert relations == []
    assert service.graph.number_of_edges() == 0


def test_reconstruct_loads_entity_relations_into_graph() -> None:
    session_factory = make_session_factory()
    with session_factory() as session:
        chunk = _seed_chunk(session)
        a = get_or_create_entity(session, name="A", entity_type="CONCEPT")
        b = get_or_create_entity(session, name="B", entity_type="CONCEPT")
        upsert_entity_relation(
            session,
            source_entity_id=a.id,
            target_entity_id=b.id,
            relation_type="uses",
            description="",
            source_chunk_id=chunk.id,
        )
        session.commit()

    service = EntityGraphService(extractor=FakeExtractor(ExtractionResult()))
    with session_factory() as session:
        service.reconstruct(session)

    assert service.graph.number_of_edges() == 1


def test_detect_communities_groups_densely_connected_entities() -> None:
    service = EntityGraphService(extractor=FakeExtractor(ExtractionResult()))
    # 두 개의 분리된 삼각형 클러스터를 만든다.
    service.graph.add_edge("a", "b", weight=1)
    service.graph.add_edge("b", "c", weight=1)
    service.graph.add_edge("a", "c", weight=1)
    service.graph.add_edge("x", "y", weight=1)
    service.graph.add_edge("y", "z", weight=1)
    service.graph.add_edge("x", "z", weight=1)

    communities = service.detect_communities()

    assert len(communities) == 2
    assert {"a", "b", "c"} in communities
    assert {"x", "y", "z"} in communities


def test_detect_communities_handles_empty_graph() -> None:
    service = EntityGraphService(extractor=FakeExtractor(ExtractionResult()))

    assert service.detect_communities() == []


def test_find_related_chunk_ids_follows_entity_graph_edge() -> None:
    from src.crud.entity import record_chunk_entity

    session_factory = make_session_factory()
    service = EntityGraphService(extractor=FakeExtractor(ExtractionResult()))
    service.graph.add_edge("entity-a", "entity-b")

    with session_factory() as session:
        chunk_a = _seed_chunk(session, chunk_id="chunk-a")
        chunk_b = _seed_chunk(session, chunk_id="chunk-b")
        record_chunk_entity(session, chunk_id=chunk_a.id, entity_id="entity-a", mention_text="A")
        record_chunk_entity(session, chunk_id=chunk_b.id, entity_id="entity-b", mention_text="B")
        session.commit()

        related = service.find_related_chunk_ids(
            session, chunk_a.id, exclude_chunk_ids=set(), max_results=10
        )

    assert related == [chunk_b.id]


def test_find_related_chunk_ids_respects_max_results_and_exclusions() -> None:
    from src.crud.entity import record_chunk_entity

    session_factory = make_session_factory()
    service = EntityGraphService(extractor=FakeExtractor(ExtractionResult()))
    service.graph.add_edge("entity-a", "entity-b")

    with session_factory() as session:
        chunk_a = _seed_chunk(session, chunk_id="chunk-a")
        chunk_b = _seed_chunk(session, chunk_id="chunk-b")
        record_chunk_entity(session, chunk_id=chunk_a.id, entity_id="entity-a", mention_text="A")
        record_chunk_entity(session, chunk_id=chunk_b.id, entity_id="entity-b", mention_text="B")
        session.commit()

        excluded = service.find_related_chunk_ids(
            session, chunk_a.id, exclude_chunk_ids={chunk_b.id}, max_results=10
        )
        zero_limit = service.find_related_chunk_ids(
            session, chunk_a.id, exclude_chunk_ids=set(), max_results=0
        )

    assert excluded == []
    assert zero_limit == []
