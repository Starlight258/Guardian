from __future__ import annotations

from fastapi.testclient import TestClient

import src.service.recall_trigger as recall_trigger
from src.main import app
from src.service.recall_trigger import RecallTriggerResult

client = TestClient(app)


def test_prompt_event_discards_short_prompt() -> None:
    response = client.post("/events/prompt", json={"prompt": "thanks"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "discarded",
        "token_count": 1,
        "min_tokens": 50,
        "recall_triggered": False,
        "reason": "below_min_tokens",
    }


def test_prompt_event_triggers_recall_for_long_prompt(monkeypatch) -> None:
    prompt = " ".join(f"token{i}" for i in range(50))
    captured_contexts = []

    def fake_dispatch(context):
        captured_contexts.append(context)
        return RecallTriggerResult(
            status="accepted",
            token_count=context.token_count,
            recall_triggered=True,
        )

    monkeypatch.setattr(recall_trigger, "dispatch_recall", fake_dispatch)

    response = client.post(
        "/events/prompt",
        json={
            "prompt": prompt,
            "session_id": "session-1",
            "cwd": "/tmp/guardian",
            "transcript_path": "/tmp/transcript.jsonl",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "token_count": 50,
        "min_tokens": 50,
        "recall_triggered": True,
        "reason": None,
    }
    assert len(captured_contexts) == 1
    context = captured_contexts[0]
    assert context.prompt == prompt
    assert context.token_count == 50
    assert context.session_id == "session-1"
    assert context.cwd == "/tmp/guardian"
    assert context.transcript_path == "/tmp/transcript.jsonl"


def test_prompt_event_requires_prompt_text() -> None:
    response = client.post("/events/prompt", json={"session_id": "session-1"})

    assert response.status_code == 422
