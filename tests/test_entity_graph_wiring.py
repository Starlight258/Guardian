from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import Base
from src.models import Chunk
from src.service.checkpoint import SessionCheckpoint, capture_session_checkpoint
from src.service.note_save import save_obsidian_note


def make_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class FakeEntityGraphService:
    def __init__(self) -> None:
        self.extracted_chunk_ids: list[str] = []
        self.reconstruct_calls = 0

    def extract_and_store(self, session: Session, chunk: Chunk) -> None:
        del session
        self.extracted_chunk_ids.append(chunk.id)

    def reconstruct(self, session: Session) -> None:
        del session
        self.reconstruct_calls += 1


def test_save_obsidian_note_extracts_entities_for_new_chunks(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    entity_graph_service = FakeEntityGraphService()
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        save_obsidian_note(session, path=note_path, entity_graph_service=entity_graph_service)

    with session_factory() as session:
        chunk = session.scalar(select(Chunk))

    assert entity_graph_service.extracted_chunk_ids == [chunk.id]


def test_save_obsidian_note_skips_extraction_when_unchanged(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    entity_graph_service = FakeEntityGraphService()
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        save_obsidian_note(session, path=note_path, entity_graph_service=entity_graph_service)
    with session_factory() as session:
        save_obsidian_note(session, path=note_path, entity_graph_service=entity_graph_service)

    assert len(entity_graph_service.extracted_chunk_ids) == 1


def test_save_obsidian_note_reconstructs_entity_graph_on_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_factory = make_session_factory()
    entity_graph_service = FakeEntityGraphService()
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        monkeypatch.setattr(
            session,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("commit failed")),
        )
        with pytest.raises(RuntimeError, match="commit failed"):
            save_obsidian_note(session, path=note_path, entity_graph_service=entity_graph_service)

    assert entity_graph_service.reconstruct_calls == 1


def test_capture_session_checkpoint_extracts_entities_for_new_chunks() -> None:
    session_factory = make_session_factory()
    entity_graph_service = FakeEntityGraphService()
    checkpoint = SessionCheckpoint(session_id="session-1", session_summary="did some work")

    with session_factory() as session:
        change = capture_session_checkpoint(
            session, checkpoint=checkpoint, entity_graph_service=entity_graph_service
        )

    assert entity_graph_service.extracted_chunk_ids == [chunk.id for chunk in change.chunks]
