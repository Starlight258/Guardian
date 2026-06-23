from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.crud.source import split_markdown_content, upsert_obsidian_note_source
from src.db import Base
from src.models import Chunk, Source


def make_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def test_split_markdown_content_keeps_one_chunk_per_short_section() -> None:
    content = "# Title\n\nIntro text.\n\n## Section A\n\nBody A.\n\n## Section B\n\nBody B."

    chunks = split_markdown_content(content)

    assert len(chunks) == 3
    assert chunks[0].startswith("# Title")
    assert chunks[1].startswith("## Section A")
    assert chunks[2].startswith("## Section B")


def test_split_markdown_content_falls_back_to_sliding_window_for_long_section() -> None:
    long_body = " ".join(f"word{i}" for i in range(700))
    content = f"## Big Section\n\n{long_body}"

    chunks = split_markdown_content(content)

    assert len(chunks) > 1
    assert chunks[0].startswith("## Big Section")
    for sub_chunk in chunks[1:]:
        assert sub_chunk.startswith("## Big Section")


def test_split_markdown_content_groups_paragraphs_before_word_fallback() -> None:
    paragraph_a = " ".join(f"a{i}" for i in range(300))
    paragraph_b = " ".join(f"b{i}" for i in range(300))
    content = f"## Big Section\n\n{paragraph_a}\n\n{paragraph_b}"

    chunks = split_markdown_content(content)

    assert len(chunks) == 2
    assert paragraph_a in chunks[0]
    assert paragraph_b not in chunks[0]
    assert chunks[1].startswith("## Big Section")
    assert paragraph_b in chunks[1]
    assert "a299" in chunks[1]  # last paragraph of previous chunk carried over as overlap


def test_split_markdown_content_splits_single_oversized_paragraph_by_words() -> None:
    long_paragraph = " ".join(f"word{i}" for i in range(700))
    content = f"## Big Section\n\n{long_paragraph}"

    chunks = split_markdown_content(content)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.startswith("## Big Section")


def test_split_markdown_content_without_headers_uses_sliding_window() -> None:
    long_body = " ".join(f"word{i}" for i in range(700))

    chunks = split_markdown_content(long_body)

    assert len(chunks) > 1


def test_upsert_obsidian_note_source_creates_chunk_per_section(tmp_path: Path) -> None:
    session_factory = make_session_factory()
    note_path = tmp_path / "note.md"
    content = "# Note\n\n## Section A\n\nBody A.\n\n## Section B\n\nBody B."
    note_path.write_text(content)

    with session_factory() as session:
        change = upsert_obsidian_note_source(session, path=note_path, content=content)
        session.commit()

    with session_factory() as session:
        source = session.scalar(select(Source).where(Source.path == str(note_path)))
        chunks = list(session.scalars(select(Chunk).order_by(Chunk.chunk_index)))

    assert change.changed is True
    assert source is not None
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert len(chunks) == 3
    assert chunks[1].text.startswith("## Section A")
    assert chunks[2].text.startswith("## Section B")
