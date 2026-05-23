from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/reindex/status")
def reindex_status(request: Request) -> dict:
    state = request.app.state.reindex_state
    return {
        "running": state.running,
        "total": state.total,
        "done": state.done,
        "skipped": state.skipped,
        "errors": state.errors,
    }
