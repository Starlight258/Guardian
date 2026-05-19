from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import Base
from src.deps import get_db
from src.main import app
from src.models import Chunk, GraphEdge, Source
from src.service.checkpoint import (
    SessionCheckpoint,
    capture_session_checkpoint,
)
from src.service.embed import VectorSearchResult
from src.service.graph import GraphService


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
        self.connected_chunk_ids: list[str] = []
        self.deleted_chunk_ids: list[str] = []

    def connect_chunks(self, session: Session, chunks: list[Chunk]) -> None:
        self.connected_chunk_ids.extend(chunk.id for chunk in chunks)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        self.deleted_chunk_ids.extend(chunk_ids)

    def reconstruct(self, session: Session) -> None:
        pass


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeVectorStore:
    def __init__(self) -> None:
        self.embeddings: dict[str, list[float]] = {}

    def upsert_chunk(self, chunk: Chunk, embedding: list[float]) -> None:
        self.embeddings[chunk.id] = embedding

    def query_similar(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        return [
            VectorSearchResult(chunk_id=chunk_id, similarity=1.0)
            for chunk_id in list(self.embeddings)[:limit]
        ]

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            self.embeddings.pop(chunk_id, None)


def test_capture_session_checkpoint_stores_source_chunk_metadata_and_connects_graph() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()
    checkpoint = SessionCheckpoint(
        session_id="session-1",
        session_summary="Implemented session checkpoint capture.",
        metadata={"cwd": "/tmp/guardian"},
    )

    with session_factory() as session:
        change = capture_session_checkpoint(
            session,
            checkpoint=checkpoint,
            graph_service=graph_service,
        )

    with session_factory() as session:
        source = session.scalar(select(Source).where(Source.session_id == checkpoint.session_id))
        chunks = list(session.scalars(select(Chunk)))

    assert change.changed is True
    assert source is not None
    assert source.source_type == "session_checkpoint"
    assert source.metadata_json == {
        "cwd": "/tmp/guardian",
        "session_id": "session-1",
        "session_summary": "Implemented session checkpoint capture.",
    }
    assert len(chunks) == 1
    assert chunks[0].source_id == source.id
    assert "Session: session-1" in chunks[0].text
    assert "Implemented session checkpoint capture." in chunks[0].text
    assert graph_service.connected_chunk_ids == [chunks[0].id]


def test_capture_session_checkpoint_splits_long_session_summary() -> None:
    session_factory = make_session_factory()
    checkpoint = SessionCheckpoint(
        session_id="session-2",
        session_summary=" ".join(f"token{i}" for i in range(700)),
    )

    with session_factory() as session:
        change = capture_session_checkpoint(session, checkpoint=checkpoint)

    with session_factory() as session:
        chunks = list(session.scalars(select(Chunk).order_by(Chunk.chunk_index)))

    assert change.changed is True
    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.token_count <= 512 for chunk in chunks)


def test_capture_session_checkpoint_creates_graph_edges_for_similar_checkpoint_chunks() -> None:
    session_factory = make_session_factory()
    vector_store = FakeVectorStore()
    graph_service = GraphService(
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        similarity_threshold=0.75,
        top_k=5,
    )

    first = SessionCheckpoint(
        session_id="session-3",
        session_summary="memory graph work",
    )
    second = SessionCheckpoint(
        session_id="session-4",
        session_summary="memory graph follow up",
    )

    with session_factory() as session:
        capture_session_checkpoint(session, checkpoint=first, graph_service=graph_service)
    with session_factory() as session:
        capture_session_checkpoint(session, checkpoint=second, graph_service=graph_service)

    with session_factory() as session:
        edges = list(session.scalars(select(GraphEdge)))
        chunks = list(session.scalars(select(Chunk)))

    assert len(edges) >= 1
    assert set(vector_store.embeddings) == {chunk.id for chunk in chunks}
    assert graph_service.graph.number_of_edges() >= 1


def test_capture_session_checkpoint_dedupes_by_session_id() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()
    checkpoint = SessionCheckpoint(
        session_id="session-5",
        session_summary="First summary.",
    )

    with session_factory() as session:
        first = capture_session_checkpoint(session, checkpoint=checkpoint, graph_service=graph_service)
    with session_factory() as session:
        second = capture_session_checkpoint(session, checkpoint=checkpoint, graph_service=graph_service)

    with session_factory() as session:
        sources = list(session.scalars(select(Source)))
        chunks = list(session.scalars(select(Chunk)))

    assert first.changed is True
    assert second.changed is False
    assert len(sources) == 1
    assert len(chunks) == 1
    assert graph_service.connected_chunk_ids == [chunks[0].id]


def test_checkpoint_event_updates_app_graph_service() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.graph_service = graph_service
    try:
        client = TestClient(app)
        response = client.post(
            "/events/checkpoint",
            json={
                "session_id": "session-6",
                "session_summary": "Captured through the running app.",
                "metadata": {"cwd": "/tmp/guardian"},
            },
        )
    finally:
        app.dependency_overrides.clear()
        del app.state.graph_service

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["chunk_count"] == 1
    assert graph_service.connected_chunk_ids


def test_session_checkpoint_hook_posts_payload_from_stdin(tmp_path: Path) -> None:
    server = _CaptureServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    try:
        subprocess.run(
            [str(Path("hooks/session_checkpoint_guardian.sh").resolve())],
            cwd=tmp_path,
            input=json.dumps(
                {
                    "session_id": "session-7",
                    "session_summary": "Rule-based checkpoint summary.",
                    "metadata": {"source": "session-end"},
                }
            ),
            text=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "GUARDIAN_URL": f"http://127.0.0.1:{server.server_port}",
            },
            check=True,
        )
    finally:
        thread.join(timeout=5)
        server.server_close()

    payload = server.payload
    assert payload["session_id"] == "session-7"
    assert payload["session_summary"] == "Rule-based checkpoint summary."
    assert payload["metadata"] == {"source": "session-end"}


def test_session_checkpoint_hook_wraps_raw_text_payload(tmp_path: Path) -> None:
    server = _CaptureServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    try:
        subprocess.run(
            [str(Path("hooks/session_checkpoint_guardian.sh").resolve())],
            cwd=tmp_path,
            input="Rule-based checkpoint summary from session end.",
            text=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "GUARDIAN_URL": f"http://127.0.0.1:{server.server_port}",
                "GUARDIAN_SESSION_ID": "session-8",
            },
            check=True,
        )
    finally:
        thread.join(timeout=5)
        server.server_close()

    payload = server.payload
    assert payload["session_id"] == "session-8"
    assert payload["session_summary"] == "Rule-based checkpoint summary from session end."
    assert payload["metadata"] == {"source": "session-end"}


def _write_transcript(path: Path, messages: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")


def _run_transcript_summary(transcript_path: Path) -> dict | None:
    hook_input = json.dumps({
        "session_id": "test-session",
        "transcript_path": str(transcript_path),
        "cwd": "/tmp",
    })
    result = subprocess.run(
        [sys.executable, str(Path("hooks/transcript_summary.py").resolve())],
        input=hook_input,
        text=True,
        capture_output=True,
    )
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def test_transcript_summary_separates_question_lines(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, [
        {"role": "user", "content": [{"type": "text", "text": "왜 이렇게 설계했어?"}]},
        {"role": "user", "content": [{"type": "text", "text": "guardian_hook.sh 연결해줘"}]},
        {"role": "user", "content": [{"type": "text", "text": "이 부분 고민이 돼"}]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "hooks/guardian_hook.sh"}},
        ]},
    ])

    payload = _run_transcript_summary(transcript)

    assert payload is not None
    summary = payload["session_summary"]
    assert "## Questions" in summary
    assert "왜 이렇게 설계했어?" in summary
    assert "이 부분 고민이 돼" in summary
    assert "## Requests" in summary
    assert "guardian_hook.sh 연결해줘" in summary
    assert "## Actions" in summary


def test_transcript_summary_question_markers(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, [
        {"role": "user", "content": [{"type": "text", "text": "뭐가 문제야?"}]},
        {"role": "user", "content": [{"type": "text", "text": "생각해보면 이건 맞는 것 같아"}]},
        {"role": "user", "content": [{"type": "text", "text": "구현해줘"}]},
    ])

    payload = _run_transcript_summary(transcript)

    assert payload is not None
    summary = payload["session_summary"]
    assert "## Questions" in summary
    assert "뭐가 문제야?" in summary
    assert "생각해보면" in summary
    assert "## Requests" in summary
    assert "구현해줘" in summary


def test_transcript_summary_only_requests_no_questions(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, [
        {"role": "user", "content": [{"type": "text", "text": "entire 의존성 제거해줘"}]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": ".claude/settings.json"}},
        ]},
    ])

    payload = _run_transcript_summary(transcript)

    assert payload is not None
    summary = payload["session_summary"]
    assert "## Questions" not in summary
    assert "## Requests" in summary


def test_transcript_summary_empty_transcript_returns_none(tmp_path: Path) -> None:
    transcript = tmp_path / "empty.jsonl"
    transcript.write_text("")

    payload = _run_transcript_summary(transcript)

    assert payload is None


class _CaptureServer(HTTPServer):
    payload: dict


class _CaptureHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        self.server.payload = json.loads(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args) -> None:
        pass
