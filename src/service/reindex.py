from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from src.db import SessionLocal
from src.service.note_save import save_obsidian_note
from src.utils import obsidian_paths_from_env

logger = logging.getLogger(__name__)


@dataclass
class ReindexState:
    total: int = 0
    done: int = 0
    errors: int = 0
    running: bool = False


def _reindex_sync(state: ReindexState, graph_service) -> None:
    vault_paths = obsidian_paths_from_env()
    files = [f for p in vault_paths for f in Path(p).rglob("*.md")]
    state.total = len(files)
    state.running = True
    logger.info("Initial reindex started — %d files", state.total)

    with SessionLocal() as session:
        for path in files:
            try:
                save_obsidian_note(session, path=path, graph_service=graph_service)
            except Exception:
                logger.warning("Reindex failed for %s", path, exc_info=True)
                state.errors += 1
            finally:
                state.done += 1
                if state.done % 100 == 0:
                    logger.info("Reindex progress: %d/%d", state.done, state.total)

    state.running = False
    logger.info("Reindex complete — %d done, %d errors", state.done, state.errors)


async def run_initial_reindex(state: ReindexState, graph_service) -> None:
    await asyncio.to_thread(_reindex_sync, state, graph_service)
