from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecallRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    context: str | None = None
    prompt: str | None = None
    user_prompt: str | None = None
    message: str | None = None
    text: str | None = None
    session_id: str | None = None
    cwd: str | None = None
    transcript_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecallResponse(BaseModel):
    status: str
    input_hash: str
    retrieved_chunk_ids: list[str]
    evidence_source_ids: list[str]
    relevance_score: float | None
    angel_triggered: bool
    drop_reason: str | None = None
    angel_message: str | None = None
