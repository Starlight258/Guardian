from __future__ import annotations

import re
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

_MARKDOWN_HEADER_PATTERN = re.compile(r"^#{1,6} .+$", re.MULTILINE)


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

    chunks = _build_chunks(source_id=source.id, texts=split_markdown_content(content))
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


def split_markdown_content(content: str) -> list[str]:
    """헤더 단위로 섹션을 나누고, 512단어를 넘는 섹션만 슬라이딩 윈도우로 추가 분할한다."""
    headers = list(_MARKDOWN_HEADER_PATTERN.finditer(content))
    if not headers:
        return split_session_checkpoint_content(content)

    sections: list[str] = []
    if headers[0].start() > 0:
        sections.append(content[: headers[0].start()])
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(content)
        sections.append(content[header.start() : end])

    chunks: list[str] = []
    for section in sections:
        section = section.strip("\n")
        if not section:
            continue
        if len(section.split()) <= CHECKPOINT_CHUNK_TOKENS:
            chunks.append(section)
            continue

        chunks.extend(_split_oversized_section(section))

    return chunks or [content]


def _split_oversized_section(section: str) -> list[str]:
    """문단(\\n\\n) 단위로 먼저 묶고, 한 문단이 너무 길면 그 문단만 단어 단위로 추가 분할한다."""
    header_match = _MARKDOWN_HEADER_PATTERN.match(section)
    header_line = header_match.group(0) if header_match else None
    body = section[len(header_line) :].lstrip("\n") if header_line else section

    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        return split_session_checkpoint_content(section)

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for paragraph in paragraphs:
        paragraph_words = len(paragraph.split())
        if paragraph_words > CHECKPOINT_CHUNK_TOKENS:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_words = 0
            chunks.extend(split_session_checkpoint_content(paragraph))
            continue

        if current and current_words + paragraph_words > CHECKPOINT_CHUNK_TOKENS:
            chunks.append("\n\n".join(current))
            overlap = current[-1]
            current = [overlap]
            current_words = len(overlap.split())

        current.append(paragraph)
        current_words += paragraph_words

    if current:
        chunks.append("\n\n".join(current))

    if header_line:
        chunks = [
            chunk if chunk.startswith(header_line) else f"{header_line}\n{chunk}"
            for chunk in chunks
        ]
    return chunks


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
        texts=split_markdown_content(content),
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
