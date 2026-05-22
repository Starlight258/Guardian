from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.mcp_server as mcp_server
from src.db import Base
from src.service.recall import RecallResult


def make_session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class FakeGraphService:
    def __init__(self) -> None:
        self.reconstruct_called = False

    def reconstruct(self, session: Session) -> None:
        del session
        self.reconstruct_called = True


class FakeRecallAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def recall(
        self,
        session: Session,
        *,
        prompt: str,
        session_id=None,
        cwd=None,
        transcript_path=None,
        metadata=None,
    ) -> RecallResult:
        del session
        payload = {
            "prompt": prompt,
            "session_id": session_id,
            "cwd": cwd,
            "transcript_path": transcript_path,
            "metadata": metadata,
        }
        self.calls.append(payload)
        return RecallResult(
            status="accepted",
            input_hash="abc123",
            retrieved_chunk_ids=["chunk-1", "chunk-2"],
            evidence_source_ids=["source-1", "source-2"],
            relevance_score=0.88,
            angel_triggered=True,
            drop_reason=None,
            angel_message="Use the cached note.",
        )


def test_recall_tool_returns_angel_payload(monkeypatch) -> None:
    graph_service = FakeGraphService()
    recall_agent = FakeRecallAgent()
    runtime = mcp_server.MCPRuntime(
        graph_service=graph_service,
        recall_agent=recall_agent,
    )
    monkeypatch.setattr(mcp_server, "_get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server, "SessionLocal", make_session_factory())

    result = mcp_server.recall(
        context="current work context",
        session_id="session-1",
        cwd="/tmp/guardian",
        metadata={"source": "claude"},
    )

    assert result["angel_message"] == "Use the cached note."
    assert result["evidence_source_ids"] == ["source-1", "source-2"]
    assert result["retrieved_chunk_ids"] == ["chunk-1", "chunk-2"]
    assert result["relevance_score"] == 0.88
    assert result["angel_triggered"] is True
    assert result["drop_reason"] is None
    assert recall_agent.calls == [
        {
            "prompt": "current work context",
            "session_id": "session-1",
            "cwd": "/tmp/guardian",
            "transcript_path": None,
            "metadata": {"source": "claude"},
        }
    ]


def test_recall_tool_uses_alternative_context_fields(monkeypatch) -> None:
    graph_service = FakeGraphService()
    recall_agent = FakeRecallAgent()
    runtime = mcp_server.MCPRuntime(
        graph_service=graph_service,
        recall_agent=recall_agent,
    )
    monkeypatch.setattr(mcp_server, "_get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server, "SessionLocal", make_session_factory())

    result = mcp_server.recall(prompt="fallback context")

    assert result["angel_message"] == "Use the cached note."
    assert recall_agent.calls[0]["prompt"] == "fallback context"


def test_recall_tool_requires_context_text(monkeypatch) -> None:
    graph_service = FakeGraphService()
    recall_agent = FakeRecallAgent()
    runtime = mcp_server.MCPRuntime(
        graph_service=graph_service,
        recall_agent=recall_agent,
    )
    monkeypatch.setattr(mcp_server, "_get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server, "SessionLocal", make_session_factory())

    try:
        mcp_server.recall()
    except ValueError as exc:
        assert "requires context text" in str(exc)
    else:  # pragma: no cover - defensive test guard
        raise AssertionError("Expected ValueError")
