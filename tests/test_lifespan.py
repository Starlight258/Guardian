from __future__ import annotations

from fastapi.testclient import TestClient

import src.main as main


class FakeWatcher:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class FakeGraphService:
    def __init__(self) -> None:
        self.reconstructed = False

    def reconstruct(self, session) -> None:
        self.reconstructed = True


def test_lifespan_starts_and_stops_configured_watcher(monkeypatch) -> None:
    watcher = FakeWatcher()
    monkeypatch.setattr(main, "create_watchers_from_env", lambda **kwargs: [watcher])
    monkeypatch.setattr(main, "GraphService", FakeGraphService)

    with TestClient(main.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert watcher.started is True
        assert main.app.state.obsidian_watchers == [watcher]
        assert main.app.state.graph_service.reconstructed is True

    assert watcher.stopped is True
