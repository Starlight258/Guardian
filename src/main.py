from __future__ import annotations

from fastapi import FastAPI

from src.api.events import router as events_router

app = FastAPI(title="Guardian", version="0.1.0")
app.include_router(events_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
