from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from watchdog.events import FileCreatedEvent

from src.db import Base
from src.models import Chunk, GraphEdge, Source
from src.service.note_ingest import delete_obsidian_note, ingest_obsidian_note, move_obsidian_note
from src.service.watcher import ObsidianEventHandler
from src.utils import OBSIDIAN_PATHS_ENV, obsidian_paths_from_env


def make_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def test_ingest_obsidian_note_creates_source_and_chunk(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path)

    with session_factory() as session:
        source = session.scalar(select(Source).where(Source.path == str(note_path)))
        chunks = list(session.scalars(select(Chunk)))

    assert source is not None
    assert source.title == "note"
    assert len(chunks) == 1
    assert chunks[0].source_id == source.id
    assert chunks[0].text == "alpha beta gamma"


def test_ingest_obsidian_note_updates_existing_source_and_replaces_chunk(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    note_path = tmp_path / "note.md"
    note_path.write_text("first version", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path)

    note_path.write_text("second version with more text", encoding="utf-8")
    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path)

    with session_factory() as session:
        sources = list(session.scalars(select(Source)))
        chunks = list(session.scalars(select(Chunk)))

    assert len(sources) == 1
    assert len(chunks) == 1
    assert chunks[0].text == "second version with more text"


def test_ingest_obsidian_note_skips_unchanged_content(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    note_path = tmp_path / "note.md"
    note_path.write_text("same content", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path)

    with session_factory() as session:
        original_chunk = session.scalar(select(Chunk))
        assert original_chunk is not None
        original_chunk_id = original_chunk.id

    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path)

    with session_factory() as session:
        chunks = list(session.scalars(select(Chunk)))

    assert len(chunks) == 1
    assert chunks[0].id == original_chunk_id


def test_delete_obsidian_note_removes_source_and_chunks(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path)
    with session_factory() as session:
        delete_obsidian_note(session, path=note_path)

    with session_factory() as session:
        source = session.scalar(select(Source).where(Source.path == str(note_path)))
        chunk_count = len(list(session.scalars(select(Chunk))))

    assert source is None
    assert chunk_count == 0


def test_delete_obsidian_note_removes_graph_edges_for_chunks(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=note_path)
        chunk = session.scalar(select(Chunk))
        assert chunk is not None
        other_source = Source(
            id=str(uuid4()),
            source_type="obsidian_note",
            title="other",
            path=str(tmp_path / "other.md"),
            metadata_json={},
            content_hash="other",
        )
        other_chunk = Chunk(
            id=str(uuid4()),
            source_id=other_source.id,
            chunk_index=0,
            text="other",
            token_count=1,
            content_hash="other",
        )
        session.add_all([other_source, other_chunk])
        session.flush()
        session.add(
            GraphEdge(
                from_chunk_id=chunk.id,
                to_chunk_id=other_chunk.id,
                similarity=0.9,
            )
        )
        session.commit()

    with session_factory() as session:
        delete_obsidian_note(session, path=note_path)

    with session_factory() as session:
        edge_count = len(list(session.scalars(select(GraphEdge))))
        remaining_chunks = list(session.scalars(select(Chunk)))

    assert edge_count == 0
    assert len(remaining_chunks) == 1
    assert remaining_chunks[0].text == "other"


def test_move_obsidian_note_updates_source_path(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    old_path = tmp_path / "old.md"
    new_path = tmp_path / "new.md"
    old_path.write_text("alpha beta gamma", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=old_path)
    old_path.rename(new_path)
    with session_factory() as session:
        move_obsidian_note(session, old_path=old_path, new_path=new_path)

    with session_factory() as session:
        old_source = session.scalar(select(Source).where(Source.path == str(old_path)))
        new_source = session.scalar(select(Source).where(Source.path == str(new_path)))

    assert old_source is None
    assert new_source is not None
    assert new_source.title == "new"


def test_move_obsidian_note_merges_when_target_source_exists(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    old_path = tmp_path / "old.md"
    new_path = tmp_path / "new.md"
    old_path.write_text("old content", encoding="utf-8")
    new_path.write_text("new content", encoding="utf-8")

    with session_factory() as session:
        ingest_obsidian_note(session, path=old_path)
        ingest_obsidian_note(session, path=new_path)

    old_path.unlink()
    with session_factory() as session:
        move_obsidian_note(session, old_path=old_path, new_path=new_path)

    with session_factory() as session:
        active_sources = list(
            session.scalars(select(Source).where(Source.path == str(new_path)))
        )
        deleted_old = session.scalar(select(Source).where(Source.path == str(old_path)))
        chunks = list(session.scalars(select(Chunk)))

    assert len(active_sources) == 1
    assert deleted_old is None
    assert len(chunks) == 1
    assert chunks[0].text == "new content"


def test_watcher_debounces_repeated_create_events(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    note_path = tmp_path / "note.md"
    note_path.write_text("alpha beta gamma", encoding="utf-8")
    handler = ObsidianEventHandler(session_factory=session_factory, debounce_ms=50)
    event = FileCreatedEvent(str(note_path))

    handler.on_created(event)
    handler.on_created(event)
    time.sleep(0.15)

    with session_factory() as session:
        sources = list(session.scalars(select(Source)))
        chunks = list(session.scalars(select(Chunk)))

    assert len(sources) == 1
    assert len(chunks) == 1


def test_obsidian_paths_from_env_supports_multiple_paths(monkeypatch, tmp_path: Path) -> None:
    vault_a = tmp_path / "vault-a"
    vault_b = tmp_path / "vault-b"
    missing = tmp_path / "missing"
    vault_a.mkdir()
    vault_b.mkdir()
    monkeypatch.setenv(
        OBSIDIAN_PATHS_ENV,
        f"{vault_a}{os.pathsep}{vault_b}{os.pathsep}{vault_a}{os.pathsep}{missing}",
    )

    assert obsidian_paths_from_env() == [vault_a.resolve(), vault_b.resolve()]
