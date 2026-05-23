# 세션 체크포인트 저장: 요약을 소스로 upsert하고 그래프를 업데이트한다.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from src.crud.source import SourceChunkChange, upsert_session_checkpoint_source
from src.service.graph import GraphService


@dataclass(frozen=True)
class SessionCheckpoint:
    session_id: str
    session_summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


def capture_session_checkpoint(
    session: Session,
    *,
    checkpoint: SessionCheckpoint,
    graph_service: GraphService | None = None,
) -> SourceChunkChange:
    change = upsert_session_checkpoint_source(
        session,
        session_id=checkpoint.session_id,
        session_summary=checkpoint.session_summary,
        metadata_json=checkpoint.metadata,
    )
    try:
        if graph_service is not None and change.changed:
            session.flush()
            graph_service.connect_chunks(session, change.chunks)
        session.commit()
    except Exception:
        session.rollback()
        if graph_service is not None and change.changed:
            graph_service.delete_chunks([chunk.id for chunk in change.chunks])
            graph_service.reconstruct(session)
        raise
    return change
