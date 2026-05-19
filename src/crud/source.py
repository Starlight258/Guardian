from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.crud.chunk import delete_source_chunks, replace_source_chunks
from src.models import Chunk, Source
from src.utils import count_tokens, hash_text

OBSIDIAN_SOURCE_TYPE = "obsidian_note"


@dataclass(frozen=True)
class SourceChunkChange:
    source: Source
    chunks: list[Chunk]
    deleted_chunk_ids: list[str]
    changed: bool


@dataclass(frozen=True)
class SourceDeleteChange:
    source: Source | None
    deleted_chunk_ids: list[str]


def upsert_obsidian_note_source(
    session: Session,
    *,
    path: Path,
    content: str,
) -> SourceChunkChange:
    normalized_path = str(path)
    source = session.scalar(
        select(Source).where(
            Source.source_type == OBSIDIAN_SOURCE_TYPE,
            Source.path == normalized_path,
        )
    )

    content_hash = hash_text(content)
    if source is None:
        source = Source(
            id=str(uuid4()),
            source_type=OBSIDIAN_SOURCE_TYPE,
            title=path.stem,
            path=normalized_path,
            metadata_json={},
            content_hash=content_hash,
        )
        session.add(source)
        session.flush()
    else:
        if source.content_hash == content_hash:
            return SourceChunkChange(
                source=source,
                chunks=[],
                deleted_chunk_ids=[],
                changed=False,
            )

        source.title = path.stem
        source.content_hash = content_hash

    chunk = Chunk(
        id=str(uuid4()),
        source_id=source.id,
        chunk_index=0,
        text=content,
        token_count=count_tokens(content),
        content_hash=content_hash,
    )
    deleted_chunk_ids = replace_source_chunks(
        session,
        source_id=source.id,
        chunks=[chunk],
    )
    return SourceChunkChange(
        source=source,
        chunks=[chunk],
        deleted_chunk_ids=deleted_chunk_ids,
        changed=True,
    )


def delete_obsidian_note_source(session: Session, *, path: Path) -> SourceDeleteChange:
    source = session.scalar(
        select(Source).where(
            Source.source_type == OBSIDIAN_SOURCE_TYPE,
            Source.path == str(path),
        )
    )
    if source is None:
        return SourceDeleteChange(source=None, deleted_chunk_ids=[])

    deleted_chunk_ids = delete_source_chunks(session, source_id=source.id)
    session.execute(delete(Source).where(Source.id == source.id))
    return SourceDeleteChange(source=source, deleted_chunk_ids=deleted_chunk_ids)


def move_obsidian_note_source(
    session: Session,
    *,
    old_path: Path,
    new_path: Path,
) -> SourceDeleteChange:
    source = session.scalar(
        select(Source).where(
            Source.source_type == OBSIDIAN_SOURCE_TYPE,
            Source.path == str(old_path),
        )
    )
    target = session.scalar(
        select(Source).where(
            Source.source_type == OBSIDIAN_SOURCE_TYPE,
            Source.path == str(new_path),
        )
    )
    if source is None:
        return SourceDeleteChange(source=target, deleted_chunk_ids=[])

    if target is not None and target.id != source.id:
        deleted_chunk_ids = delete_source_chunks(session, source_id=source.id)
        session.execute(delete(Source).where(Source.id == source.id))
        target.title = new_path.stem
        return SourceDeleteChange(source=target, deleted_chunk_ids=deleted_chunk_ids)

    source.path = str(new_path)
    source.title = new_path.stem
    return SourceDeleteChange(source=source, deleted_chunk_ids=[])
