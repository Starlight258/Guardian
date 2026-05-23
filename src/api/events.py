# 이벤트 라우터: /prompt, /session-checkpoint 엔드포인트.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.deps import get_db
from src.schemas.events import (
    PromptEventRequest,
    PromptEventResponse,
    SessionCheckpointRequest,
    SessionCheckpointResponse,
)
from src.service.checkpoint import SessionCheckpoint, capture_session_checkpoint
from src.service.recall_trigger import MIN_PROMPT_TOKENS, trigger_recall_from_prompt

router = APIRouter(prefix="/events", tags=["events"])
DBSession = Depends(get_db)


def _extract_prompt(event: PromptEventRequest) -> str:
    # hook 페이로드 형태가 다양해 여러 필드명을 순서대로 시도한다.
    for value in (event.prompt, event.user_prompt, event.message, event.text):
        if value and value.strip():
            return value.strip()
    raise HTTPException(status_code=422, detail="Prompt event must include prompt text")


@router.post("/prompt", response_model=PromptEventResponse)
def receive_prompt_event(
    event: PromptEventRequest,
    request: Request,
    db: Session = DBSession,
) -> PromptEventResponse:
    prompt = _extract_prompt(event)
    recall_agent = getattr(request.app.state, "recall_agent", None)
    result = trigger_recall_from_prompt(
        prompt=prompt,
        session_id=event.session_id,
        cwd=event.cwd,
        transcript_path=event.transcript_path,
        metadata=event.metadata,
        db=db,
        recall_agent=recall_agent,
    )

    return PromptEventResponse(
        status=result.status,
        token_count=result.token_count,
        min_tokens=MIN_PROMPT_TOKENS,
        recall_triggered=result.recall_triggered,
        reason=result.reason,
    )


@router.post("/session-checkpoint", response_model=SessionCheckpointResponse)
def receive_checkpoint_event(
    event: SessionCheckpointRequest,
    request: Request,
    db: Session = DBSession,
) -> SessionCheckpointResponse:
    graph_service = getattr(request.app.state, "graph_service", None)
    change = capture_session_checkpoint(
        db,
        checkpoint=SessionCheckpoint(
            session_id=event.session_id,
            session_summary=event.session_summary,
            metadata=event.metadata,
        ),
        graph_service=graph_service,
    )
    return SessionCheckpointResponse(
        status="deduped" if not change.changed else "accepted",
        source_id=change.source.id,
        chunk_count=len(change.chunks),
        deduped=not change.changed,
    )
