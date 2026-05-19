from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from src.api.events import router as events_router
from src.api.graph import router as graph_router
from src.db import SessionLocal
from src.service.graph import GraphService
from src.service.watcher import create_watchers_from_env

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    graph_service = GraphService()
    with SessionLocal() as session:
        graph_service.reconstruct(session)
    app.state.graph_service = graph_service

    watchers = create_watchers_from_env(graph_service=graph_service)
    for watcher in watchers:
        watcher.start()
    app.state.obsidian_watchers = watchers
    try:
        yield
    finally:
        for watcher in watchers:
            watcher.stop()


app = FastAPI(title="Guardian", version="0.1.0", lifespan=lifespan)
app.include_router(events_router)
app.include_router(graph_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
