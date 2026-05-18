from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from src.crud.source import (
    delete_obsidian_note_source,
    move_obsidian_note_source,
    upsert_obsidian_note_source,
)


def ingest_obsidian_note(session: Session, *, path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    content = path.read_text(encoding="utf-8")
    upsert_obsidian_note_source(session, path=path, content=content)
    session.commit()


def delete_obsidian_note(session: Session, *, path: Path) -> None:
    delete_obsidian_note_source(session, path=path)
    session.commit()


def move_obsidian_note(session: Session, *, old_path: Path, new_path: Path) -> None:
    move_obsidian_note_source(session, old_path=old_path, new_path=new_path)
    session.commit()
