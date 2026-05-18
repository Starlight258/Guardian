from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptEventRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str | None = None
    user_prompt: str | None = None
    message: str | None = None
    text: str | None = None
    session_id: str | None = None
    cwd: str | None = None
    transcript_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptEventResponse(BaseModel):
    status: str
    token_count: int
    min_tokens: int
    recall_triggered: bool
    reason: str | None = None
