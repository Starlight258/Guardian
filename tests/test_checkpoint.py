from __future__ import annotations

import json
import subprocess
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
    GitCheckpoint,
    capture_git_checkpoint,
    checkpoint_from_git,
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


def test_capture_git_checkpoint_stores_source_chunk_metadata_and_connects_graph() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()
    checkpoint = GitCheckpoint(
        commit_sha="a" * 40,
        commit_message="feat: add memory graph",
        branch="main",
        changed_files=["src/service/checkpoint.py", "tests/test_checkpoint.py"],
        session_summary="Implemented checkpoint capture.",
    )

    with session_factory() as session:
        change = capture_git_checkpoint(
            session,
            checkpoint=checkpoint,
            graph_service=graph_service,
        )

    with session_factory() as session:
        source = session.scalar(select(Source).where(Source.commit_sha == checkpoint.commit_sha))
        chunks = list(session.scalars(select(Chunk)))

    assert change.changed is True
    assert source is not None
    assert source.source_type == "git_checkpoint"
    assert source.metadata_json == {
        "branch": "main",
        "changed_files": ["src/service/checkpoint.py", "tests/test_checkpoint.py"],
        "commit_message": "feat: add memory graph",
        "session_summary": "Implemented checkpoint capture.",
    }
    assert len(chunks) == 1
    assert chunks[0].source_id == source.id
    assert "Commit: " + checkpoint.commit_sha in chunks[0].text
    assert "- src/service/checkpoint.py" in chunks[0].text
    assert graph_service.connected_chunk_ids == [chunks[0].id]


def test_capture_git_checkpoint_splits_long_session_summary() -> None:
    session_factory = make_session_factory()
    checkpoint = GitCheckpoint(
        commit_sha="c" * 40,
        commit_message="feat: summarize long session",
        branch="main",
        changed_files=["src/service/checkpoint.py"],
        session_summary=" ".join(f"token{i}" for i in range(700)),
    )

    with session_factory() as session:
        change = capture_git_checkpoint(session, checkpoint=checkpoint)

    with session_factory() as session:
        chunks = list(session.scalars(select(Chunk).order_by(Chunk.chunk_index)))

    assert change.changed is True
    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.token_count <= 512 for chunk in chunks)


def test_capture_git_checkpoint_creates_graph_edges_for_similar_checkpoint_chunks() -> None:
    session_factory = make_session_factory()
    vector_store = FakeVectorStore()
    graph_service = GraphService(
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        similarity_threshold=0.75,
        top_k=5,
    )

    first = GitCheckpoint(
        commit_sha="d" * 40,
        commit_message="feat: first checkpoint",
        branch="main",
        changed_files=["src/first.py"],
        session_summary="memory graph work",
    )
    second = GitCheckpoint(
        commit_sha="e" * 40,
        commit_message="feat: second checkpoint",
        branch="main",
        changed_files=["src/second.py"],
        session_summary="memory graph follow up",
    )

    with session_factory() as session:
        capture_git_checkpoint(session, checkpoint=first, graph_service=graph_service)
    with session_factory() as session:
        capture_git_checkpoint(session, checkpoint=second, graph_service=graph_service)

    with session_factory() as session:
        edges = list(session.scalars(select(GraphEdge)))
        chunks = list(session.scalars(select(Chunk)))

    assert len(edges) >= 1
    assert set(vector_store.embeddings) == {chunk.id for chunk in chunks}
    assert graph_service.graph.number_of_edges() >= 1


def test_capture_git_checkpoint_dedupes_by_commit_sha() -> None:
    session_factory = make_session_factory()
    graph_service = FakeGraphService()
    checkpoint = GitCheckpoint(
        commit_sha="b" * 40,
        commit_message="fix: keep checkpoint idempotent",
        branch="main",
        changed_files=["src/service/checkpoint.py"],
        session_summary="First summary.",
    )

    with session_factory() as session:
        first = capture_git_checkpoint(session, checkpoint=checkpoint, graph_service=graph_service)
    with session_factory() as session:
        second = capture_git_checkpoint(session, checkpoint=checkpoint, graph_service=graph_service)

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
                "commit_sha": "f" * 40,
                "commit_message": "feat: endpoint capture",
                "branch": "main",
                "changed_files": ["src/api/events.py"],
                "session_summary": "Captured through the running app.",
            },
        )
    finally:
        app.dependency_overrides.clear()
        del app.state.graph_service

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["chunk_count"] == 1
    assert graph_service.connected_chunk_ids


def test_checkpoint_from_git_collects_commit_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "guardian@example.com")
    _git(repo, "config", "user.name", "Guardian")
    note = repo / "note.md"
    note.write_text("memory", encoding="utf-8")
    _git(repo, "add", "note.md")
    _git(repo, "commit", "-m", "docs: add note")

    checkpoint = checkpoint_from_git(repo)

    assert len(checkpoint.commit_sha) == 40
    assert checkpoint.commit_message == "docs: add note"
    assert checkpoint.branch in {"main", "master"}
    assert checkpoint.changed_files == ["note.md"]
    assert checkpoint.session_summary == "docs: add note"


def test_post_commit_hook_posts_checkpoint_from_external_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "guardian@example.com")
    _git(repo, "config", "user.name", "Guardian")
    note = repo / "note.md"
    note.write_text("memory", encoding="utf-8")
    _git(repo, "add", "note.md")
    _git(repo, "commit", "-m", "docs: add note")
    server = _CaptureServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    try:
        subprocess.run(
            [str(Path("hooks/post_commit_guardian.sh").resolve())],
            cwd=repo,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "GUARDIAN_URL": f"http://127.0.0.1:{server.server_port}",
                "GUARDIAN_CHECKPOINT_SUMMARY": "External repo summary",
            },
            check=True,
        )
    finally:
        thread.join(timeout=5)
        server.server_close()

    payload = server.payload
    assert payload["commit_message"] == "docs: add note"
    assert payload["changed_files"] == ["note.md"]
    assert payload["session_summary"] == "External repo summary"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


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
