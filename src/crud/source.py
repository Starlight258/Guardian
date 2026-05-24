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
SESSION_CHECKPOINT_SOURCE_TYPE = "session_checkpoint"
CHECKPOINT_CHUNK_TOKENS = 512
CHECKPOINT_CHUNK_OVERLAP_RATIO = 0.2


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

    file_mtime = path.stat().st_mtime
    content_hash = hash_text(content)
    if source is None:
        source = Source(
            id=str(uuid4()),
            source_type=OBSIDIAN_SOURCE_TYPE,
            title=path.stem,
            path=normalized_path,
            metadata_json={},
            content_hash=content_hash,
            file_mtime=file_mtime,
        )
        session.add(source)
        session.flush()
    else:
        source.file_mtime = file_mtime
        if source.content_hash == content_hash:
            return SourceChunkChange(
                source=source,
                chunks=[],
                deleted_chunk_ids=[],
                changed=False,
            )

        source.title = path.stem
        source.content_hash = content_hash

    chunks = _build_chunks(source_id=source.id, texts=[content])
    deleted_chunk_ids = replace_source_chunks(
        session,
        source_id=source.id,
        chunks=chunks,
    )
    return SourceChunkChange(
        source=source,
        chunks=chunks,
        deleted_chunk_ids=deleted_chunk_ids,
        changed=True,
    )


def upsert_session_checkpoint_source(
    session: Session,
    *,
    session_id: str,
    session_summary: str,
    metadata_json: dict | None = None,
) -> SourceChunkChange:
    source = session.scalar(
        select(Source).where(
            Source.source_type == SESSION_CHECKPOINT_SOURCE_TYPE,
            Source.session_id == session_id,
        )
    )
    content = render_session_checkpoint_content(
        session_id=session_id,
        session_summary=session_summary,
    )
    content_hash = hash_text(content)
    stored_metadata = dict(metadata_json or {})
    stored_metadata["session_id"] = session_id
    stored_metadata["session_summary"] = session_summary

    if source is None:
        source = Source(
            id=str(uuid4()),
            source_type=SESSION_CHECKPOINT_SOURCE_TYPE,
            title=f"Session checkpoint {session_id[:12]}",
            path=None,
            session_id=session_id,
            commit_sha=None,
            metadata_json=stored_metadata,
            content_hash=content_hash,
        )
        session.add(source)
        session.flush()
    else:
        if (
            source.content_hash == content_hash
            and source.metadata_json == stored_metadata
            and source.title == f"Session checkpoint {session_id[:12]}"
        ):
            return SourceChunkChange(
                source=source,
                chunks=[],
                deleted_chunk_ids=[],
                changed=False,
            )

        source.title = f"Session checkpoint {session_id[:12]}"
        source.metadata_json = stored_metadata
        source.content_hash = content_hash

    chunks = _build_chunks(
        source_id=source.id,
        texts=split_session_checkpoint_content(content),
    )
    deleted_chunk_ids = replace_source_chunks(
        session,
        source_id=source.id,
        chunks=chunks,
    )
    return SourceChunkChange(
        source=source,
        chunks=chunks,
        deleted_chunk_ids=deleted_chunk_ids,
        changed=True,
    )


def render_session_checkpoint_content(*, session_id: str, session_summary: str) -> str:
    return "\n".join(
        [
            "# Session checkpoint",
            "",
            f"Session: {session_id}",
            "",
            "## Session summary",
            session_summary.strip(),
        ]
    )


def split_session_checkpoint_content(content: str) -> list[str]:
    words = content.split()
    if len(words) <= CHECKPOINT_CHUNK_TOKENS:
        return [content]

    chunks: list[str] = []
    overlap = int(CHECKPOINT_CHUNK_TOKENS * CHECKPOINT_CHUNK_OVERLAP_RATIO)
    step = CHECKPOINT_CHUNK_TOKENS - overlap
    for start in range(0, len(words), step):
        window = words[start : start + CHECKPOINT_CHUNK_TOKENS]
        if not window:
            break
        chunks.append(" ".join(window))
        if start + CHECKPOINT_CHUNK_TOKENS >= len(words):
            break
    return chunks


def _build_chunks(*, source_id: str, texts: list[str]) -> list[Chunk]:
    return [
        Chunk(
            id=str(uuid4()),
            source_id=source_id,
            chunk_index=index,
            text=text,
            token_count=count_tokens(text),
            content_hash=hash_text(text),
        )
        for index, text in enumerate(texts)
    ]


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
