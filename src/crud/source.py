from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.crud.chunk import delete_source_chunks, replace_source_chunks
from src.models import Chunk, Source
from src.utils import count_tokens, hash_text

OBSIDIAN_SOURCE_TYPE = "obsidian_note"


def upsert_obsidian_note_source(
    session: Session,
    *,
    path: Path,
    content: str,
) -> Source:
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
            return source

        source.title = path.stem
        source.content_hash = content_hash

    replace_source_chunks(
        session,
        source_id=source.id,
        chunks=[
            Chunk(
                id=str(uuid4()),
                source_id=source.id,
                chunk_index=0,
                text=content,
                token_count=count_tokens(content),
                content_hash=content_hash,
            )
        ],
    )
    return source


def delete_obsidian_note_source(session: Session, *, path: Path) -> Source | None:
    source = session.scalar(
        select(Source).where(
            Source.source_type == OBSIDIAN_SOURCE_TYPE,
            Source.path == str(path),
        )
    )
    if source is None:
        return None

    delete_source_chunks(session, source_id=source.id)
    session.execute(delete(Source).where(Source.id == source.id))
    return source


def move_obsidian_note_source(session: Session, *, old_path: Path, new_path: Path) -> Source | None:
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
        return target

    if target is not None and target.id != source.id:
        delete_source_chunks(session, source_id=source.id)
        session.execute(delete(Source).where(Source.id == source.id))
        target.title = new_path.stem
        return target

    source.path = str(new_path)
    source.title = new_path.stem
    return source
