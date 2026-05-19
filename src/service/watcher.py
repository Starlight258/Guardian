from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session
from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.db import SessionLocal
from src.service.graph import GraphService
from src.service.note_save import delete_obsidian_note, move_obsidian_note, save_obsidian_note
from src.utils import obsidian_paths_from_env

SessionFactory = Callable[[], Session]


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
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        debounce_ms: int = 300,
        graph_service: GraphService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._graph_service = graph_service
        self._debouncer = Debouncer(debounce_ms / 1000)

    def on_created(self, event: FileSystemEvent) -> None:
        if _is_markdown_file_event(event):
            path = Path(str(event.src_path))
            self._debouncer.schedule(
                f"file:{path}",
                lambda: self._with_session(save_obsidian_note, path=path),
            )

    def on_modified(self, event: FileSystemEvent) -> None:
        if _is_markdown_file_event(event):
            path = Path(str(event.src_path))
            self._debouncer.schedule(
                f"file:{path}",
                lambda: self._with_session(save_obsidian_note, path=path),
            )

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

    def _with_session(self, callback: Callable[..., None], **kwargs) -> None:
        with self._session_factory() as session:
            if self._graph_service is not None:
                kwargs["graph_service"] = self._graph_service
            callback(session, **kwargs)


class ObsidianWatcher:
    def __init__(
        self,
        *,
        vault_path: Path,
        session_factory: SessionFactory = SessionLocal,
        debounce_ms: int = 300,
        graph_service: GraphService | None = None,
    ) -> None:
        self._vault_path = vault_path
        self._handler = ObsidianEventHandler(
            session_factory=session_factory,
            debounce_ms=debounce_ms,
            graph_service=graph_service,
        )
        self._observer = Observer()

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self._vault_path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._handler.stop()
        self._observer.stop()
        self._observer.join(timeout=5)


def create_watchers_from_env(graph_service: GraphService | None = None) -> list[ObsidianWatcher]:
    return [
        ObsidianWatcher(vault_path=path, graph_service=graph_service)
        for path in obsidian_paths_from_env()
    ]


def _is_markdown_file_event(event: FileSystemEvent) -> bool:
    if event.is_directory:
        return False
    return Path(str(event.src_path)).suffix.lower() == ".md"
