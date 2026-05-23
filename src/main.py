from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from src.api.admin import router as admin_router
from src.api.events import router as events_router
from src.api.graph import router as graph_router
from src.api.recall import router as recall_router
from src.db import SessionLocal
from src.llm import make_llm_client
from src.service.graph import GraphService
from src.service.recall import RecallAgent
from src.service.reindex import ReindexState, run_initial_reindex
from src.service.watcher import create_watchers_from_env

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    graph_service = GraphService()
    with SessionLocal() as session:
        graph_service.reconstruct(session)
    app.state.graph_service = graph_service
    app.state.recall_agent = RecallAgent(graph_service=graph_service, llm_client=make_llm_client())

    watchers = create_watchers_from_env(graph_service=graph_service)
    for watcher in watchers:
        watcher.start()
    app.state.obsidian_watchers = watchers

    reindex_state = ReindexState()
    app.state.reindex_state = reindex_state
    asyncio.create_task(run_initial_reindex(reindex_state, graph_service))

    try:
        yield
    finally:
        for watcher in watchers:
            watcher.stop()


app = FastAPI(title="Guardian", version="0.1.0", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(events_router)
app.include_router(graph_router)
app.include_router(recall_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
