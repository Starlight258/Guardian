from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from src.crud.source import (
    delete_obsidian_note_source,
    move_obsidian_note_source,
    upsert_obsidian_note_source,
)
from src.service.graph import GraphService


def ingest_obsidian_note(
    session: Session,
    *,
    path: Path,
    graph_service: GraphService | None = None,
) -> None:
    if not path.exists() or not path.is_file():
        return

    content = path.read_text(encoding="utf-8")
    change = upsert_obsidian_note_source(session, path=path, content=content)
    try:
        if graph_service is not None and change.changed:
            session.flush()
            graph_service.connect_chunks(session, change.chunks)
        session.commit()
    except Exception:
        session.rollback()
        if graph_service is not None and change.changed:
            graph_service.delete_chunks([chunk.id for chunk in change.chunks])
            graph_service.reconstruct(session)
        raise

    if graph_service is not None and change.changed:
        graph_service.delete_chunks(change.deleted_chunk_ids)


def delete_obsidian_note(
    session: Session,
    *,
    path: Path,
    graph_service: GraphService | None = None,
) -> None:
    change = delete_obsidian_note_source(session, path=path)
    session.commit()
    if graph_service is not None:
        graph_service.delete_chunks(change.deleted_chunk_ids)


def move_obsidian_note(
    session: Session,
    *,
    old_path: Path,
    new_path: Path,
    graph_service: GraphService | None = None,
) -> None:
    change = move_obsidian_note_source(session, old_path=old_path, new_path=new_path)
    session.commit()
    if graph_service is not None:
        graph_service.delete_chunks(change.deleted_chunk_ids)
