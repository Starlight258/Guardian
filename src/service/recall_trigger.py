from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.utils import count_tokens

MIN_PROMPT_TOKENS = 50


@dataclass(frozen=True)
class PromptContext:
    prompt: str
    token_count: int
    session_id: str | None = None
    cwd: str | None = None
    transcript_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallTriggerResult:
    status: str
    token_count: int
    recall_triggered: bool
    reason: str | None = None


def trigger_recall_from_prompt(
    *,
    prompt: str,
    session_id: str | None = None,
    cwd: str | None = None,
    transcript_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RecallTriggerResult:
    token_count = count_tokens(prompt)
    if token_count < MIN_PROMPT_TOKENS:
        return RecallTriggerResult(
            status="discarded",
            token_count=token_count,
            recall_triggered=False,
            reason="below_min_tokens",
        )

    context = PromptContext(
        prompt=prompt,
        token_count=token_count,
        session_id=session_id,
        cwd=cwd,
        transcript_path=transcript_path,
        metadata=metadata or {},
    )
    return dispatch_recall(context)


def dispatch_recall(context: PromptContext) -> RecallTriggerResult:
    return RecallTriggerResult(
        status="accepted",
        token_count=context.token_count,
        recall_triggered=True,
    )
