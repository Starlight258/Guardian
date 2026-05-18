from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.schemas.events import PromptEventRequest, PromptEventResponse
from src.service.recall_trigger import MIN_PROMPT_TOKENS, trigger_recall_from_prompt

router = APIRouter(prefix="/events", tags=["events"])


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
