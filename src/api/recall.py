from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.deps import get_db
from src.schemas.recall import RecallRequest, RecallResponse
from src.service.recall import RecallAgent

router = APIRouter(prefix="/recall", tags=["recall"])
DBSession = Depends(get_db)


def _extract_context_text(event: RecallRequest) -> str:
    for value in (event.context, event.prompt, event.user_prompt, event.message, event.text):
        if value and value.strip():
            return value.strip()
    raise HTTPException(status_code=422, detail="Recall request must include context text")


@router.post("", response_model=RecallResponse)
def run_recall(
    event: RecallRequest,
    request: Request,
    db: Session = DBSession,
) -> RecallResponse:
    graph_service = getattr(request.app.state, "graph_service", None)
    if graph_service is None:
        raise HTTPException(status_code=503, detail="Graph service is not available")

    recall_agent = getattr(request.app.state, "recall_agent", None)
    if recall_agent is None:
        entity_graph_service = getattr(request.app.state, "entity_graph_service", None)
        recall_agent = RecallAgent(
            graph_service=graph_service, entity_graph_service=entity_graph_service
        )

    result = recall_agent.recall(
        db,
        prompt=_extract_context_text(event),
        session_id=event.session_id,
        cwd=event.cwd,
        transcript_path=event.transcript_path,
        metadata=event.metadata,
    )
    return RecallResponse(
        status=result.status,
        input_hash=result.input_hash,
        retrieved_chunk_ids=result.retrieved_chunk_ids,
        evidence_source_ids=result.evidence_source_ids,
        relevance_score=result.relevance_score,
        angel_triggered=result.angel_triggered,
        drop_reason=result.drop_reason,
        angel_message=result.angel_message,
    )
