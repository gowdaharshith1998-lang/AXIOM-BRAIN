"""Observability endpoint tests (OBS-02/03/04/05).

Uses ``with TestClient(app)`` so the FastAPI lifespan runs and populates
``app.state`` (background tasks, vault status) before the assertions.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.studio.server import create_app


def _client() -> TestClient:
    # In-memory SQLite keeps each test isolated; enable_organizer=False keeps
    # startup lightweight.
    return TestClient(create_app(db_url="sqlite://", enable_organizer=False))


def test_livez_always_200() -> None:
    with _client() as client:
        resp = client.get("/livez")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_readyz_200_when_healthy() -> None:
    # With the lifespan running, the DB is reachable and (in dev/test) the vault
    # is treated as unlocked, so /readyz should report healthy.
    with _client() as client:
        resp = client.get("/readyz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["checks"]["failed"] == []


def test_readyz_reports_checks_key() -> None:
    with _client() as client:
        resp = client.get("/readyz")
        body = resp.json()
        assert "checks" in body
        assert "failed" in body["checks"]


def test_metrics_endpoint_returns_200() -> None:
    # /metrics serves Prometheus text when prometheus-client is installed and
    # degrades gracefully (still 200) otherwise (OBS-04).
    with _client() as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200


def test_request_id_header_is_echoed() -> None:
    # X-Request-ID is generated when absent and echoed on the response (OBS-05).
    with _client() as client:
        resp = client.get("/livez")
        assert resp.headers.get("X-Request-ID")

        sent = "fixed-request-id-123"
        resp2 = client.get("/livez", headers={"X-Request-ID": sent})
        assert resp2.headers.get("X-Request-ID") == sent
