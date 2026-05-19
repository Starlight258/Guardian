from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.deps import get_db
from src.schemas.events import (
    CheckpointEventRequest,
    CheckpointEventResponse,
    PromptEventRequest,
    PromptEventResponse,
)
from src.service.checkpoint import GitCheckpoint, capture_git_checkpoint
from src.service.recall_trigger import MIN_PROMPT_TOKENS, trigger_recall_from_prompt

router = APIRouter(prefix="/events", tags=["events"])
DBSession = Depends(get_db)


def _extract_prompt(event: PromptEventRequest) -> str:
    for value in (event.prompt, event.user_prompt, event.message, event.text):
        if value and value.strip():
            return value.strip()
    raise HTTPException(status_code=422, detail="Prompt event must include prompt text")


@router.post("/prompt", response_model=PromptEventResponse)
def receive_prompt_event(event: PromptEventRequest) -> PromptEventResponse:
    prompt = _extract_prompt(event)
    result = trigger_recall_from_prompt(
        prompt=prompt,
        session_id=event.session_id,
        cwd=event.cwd,
        transcript_path=event.transcript_path,
        metadata=event.metadata,
    )

    return PromptEventResponse(
        status=result.status,
        token_count=result.token_count,
        min_tokens=MIN_PROMPT_TOKENS,
        recall_triggered=result.recall_triggered,
        reason=result.reason,
    )


@router.post("/checkpoint", response_model=CheckpointEventResponse)
def receive_checkpoint_event(
    event: CheckpointEventRequest,
    request: Request,
    db: Session = DBSession,
) -> CheckpointEventResponse:
    graph_service = getattr(request.app.state, "graph_service", None)
    change = capture_git_checkpoint(
        db,
        checkpoint=GitCheckpoint(
            commit_sha=event.commit_sha,
            commit_message=event.commit_message,
            branch=event.branch,
            changed_files=event.changed_files,
            session_summary=event.session_summary,
        ),
        graph_service=graph_service,
    )
    return CheckpointEventResponse(
        status="deduped" if not change.changed else "accepted",
        source_id=change.source.id,
        chunk_count=len(change.chunks),
        deduped=not change.changed,
    )
