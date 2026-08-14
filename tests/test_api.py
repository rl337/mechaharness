"""API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mechaharness.api.app import app


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_backends_and_families() -> None:
    client = TestClient(app)
    assert "lmstudio" in client.get("/backends").json()["backends"]
    assert "tool_loop" in client.get("/families").json()["families"]


def test_run_unknown_backend() -> None:
    client = TestClient(app)
    resp = client.post("/v1/run", json={"prompt": "hi", "backend": "nope"})
    assert resp.status_code == 400
    assert "Unknown inference backend" in resp.json()["detail"]
