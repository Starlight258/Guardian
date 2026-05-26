from __future__ import annotations

from fastapi.testclient import TestClient

import src.service.recall_trigger as recall_trigger
from src.main import app
from src.service.recall_trigger import RecallTriggerResult

client = TestClient(app)


def test_prompt_event_discards_short_prompt() -> None:
    response = client.post("/events/prompt", json={"prompt": "hi"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "discarded",
        "char_count": 2,
        "min_chars": 10,
        "recall_triggered": False,
        "reason": "below_min_chars",
    }


def test_prompt_event_triggers_recall_for_long_prompt(monkeypatch) -> None:
    prompt = "a" * 50
    captured_contexts = []

    def fake_dispatch(context, *, db=None, recall_agent=None):
        captured_contexts.append(context)
        return RecallTriggerResult(
            status="accepted",
            char_count=context.char_count,
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
        "char_count": 50,
        "min_chars": 10,
        "recall_triggered": True,
        "reason": None,
    }
    assert len(captured_contexts) == 1
    context = captured_contexts[0]
    assert context.prompt == prompt
    assert context.char_count == 50
    assert context.session_id == "session-1"
    assert context.cwd == "/tmp/guardian"
    assert context.transcript_path == "/tmp/transcript.jsonl"


def test_prompt_event_requires_prompt_text() -> None:
    response = client.post("/events/prompt", json={"session_id": "session-1"})

    assert response.status_code == 422
