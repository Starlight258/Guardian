from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session
from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.db import SessionLocal
from src.service.note_ingest import delete_obsidian_note, ingest_obsidian_note, move_obsidian_note

SessionFactory = Callable[[], Session]
OBSIDIAN_PATHS_ENV = "GUARDIAN_OBSIDIAN_PATHS"
OBSIDIAN_PATH_ENV = "GUARDIAN_OBSIDIAN_PATH"


class Debouncer:
    def __init__(self, delay_seconds: float) -> None:
        self._delay_seconds = delay_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, key: str, callback: Callable[[], None]) -> None:
        with self._lock:
            existing = self._timers.pop(key, None)
            if existing is not None:
                existing.cancel()

            timer = threading.Timer(self._delay_seconds, self._run, args=(key, callback))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def cancel_all(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()

        for timer in timers:
            timer.cancel()

    def _run(self, key: str, callback: Callable[[], None]) -> None:
        with self._lock:
            self._timers.pop(key, None)
        callback()


class ObsidianEventHandler(FileSystemEventHandler):
    def __init__(self, *, session_factory: SessionFactory, debounce_ms: int = 300) -> None:
        self._session_factory = session_factory
        self._debouncer = Debouncer(debounce_ms / 1000)

    def on_created(self, event: FileSystemEvent) -> None:
        if _is_markdown_file_event(event):
            self._schedule_ingest(Path(str(event.src_path)))

    def on_modified(self, event: FileSystemEvent) -> None:
        if _is_markdown_file_event(event):
            self._schedule_ingest(Path(str(event.src_path)))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if _is_markdown_file_event(event):
            path = Path(str(event.src_path))
            self._debouncer.schedule(
                f"file:{path}",
                lambda: self._with_session(delete_obsidian_note, path=path),
            )

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return

        old_path = Path(str(event.src_path))
        new_path = Path(str(event.dest_path))
        if old_path.suffix.lower() != ".md" and new_path.suffix.lower() != ".md":
            return

        self._debouncer.schedule(
            f"file:{old_path}",
            lambda: self._with_session(move_obsidian_note, old_path=old_path, new_path=new_path),
        )

    def stop(self) -> None:
        self._debouncer.cancel_all()

    def _schedule_ingest(self, path: Path) -> None:
        self._debouncer.schedule(
            f"file:{path}",
            lambda: self._with_session(ingest_obsidian_note, path=path),
        )

    def _with_session(self, callback: Callable[..., None], **kwargs) -> None:
        with self._session_factory() as session:
            callback(session, **kwargs)


class ObsidianWatcher:
    def __init__(
        self,
        *,
        vault_path: Path,
        session_factory: SessionFactory = SessionLocal,
        debounce_ms: int = 300,
    ) -> None:
        self._vault_path = vault_path
        self._handler = ObsidianEventHandler(
            session_factory=session_factory,
            debounce_ms=debounce_ms,
        )
        self._observer = Observer()

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self._vault_path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._handler.stop()
        self._observer.stop()
        self._observer.join(timeout=5)


def create_watchers_from_env() -> list[ObsidianWatcher]:
    return [ObsidianWatcher(vault_path=path) for path in obsidian_paths_from_env()]


def obsidian_paths_from_env() -> list[Path]:
    raw_paths = os.getenv(OBSIDIAN_PATHS_ENV) or os.getenv(OBSIDIAN_PATH_ENV)
    if not raw_paths:
        return []

    paths: list[Path] = []
    seen: set[Path] = set()
    for raw_path in raw_paths.split(os.pathsep):
        if not raw_path.strip():
            continue
        path = Path(raw_path).expanduser().resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _is_markdown_file_event(event: FileSystemEvent) -> bool:
    if event.is_directory:
        return False
    return Path(str(event.src_path)).suffix.lower() == ".md"
