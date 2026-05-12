from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from starlette.websockets import WebSocketDisconnect

from axiom.schema.models import Base
from axiom.studio.server import create_app


def _client(tmp_path: Path) -> TestClient:
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    return TestClient(create_app(db_url=db_url, enable_organizer=False))


def test_api_auth_is_disabled_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AXIOM_API_TOKEN", raising=False)
    monkeypatch.delenv("AXIOM_AUTH_REQUIRED", raising=False)

    with _client(tmp_path) as client:
        assert client.get("/api/internal/settings").status_code == 200


def test_api_auth_rejects_missing_or_wrong_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_API_TOKEN", "prod-secret")

    with _client(tmp_path) as client:
        missing = client.get("/api/internal/settings")
        wrong = client.get(
            "/api/internal/settings",
            headers={"Authorization": "Bearer wrong-secret"},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_api_auth_accepts_bearer_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_API_TOKEN", "prod-secret")

    with _client(tmp_path) as client:
        response = client.get(
            "/api/internal/settings",
            headers={"Authorization": "Bearer prod-secret"},
        )

    assert response.status_code == 200


def test_health_endpoint_stays_public_when_auth_is_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_API_TOKEN", "prod-secret")

    with _client(tmp_path) as client:
        response = client.get("/api/health")

    assert response.status_code == 200


def test_api_auth_required_without_token_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AXIOM_API_TOKEN", raising=False)
    monkeypatch.setenv("AXIOM_AUTH_REQUIRED", "1")

    with _client(tmp_path) as client:
        response = client.get("/api/internal/settings")

    assert response.status_code == 503


def test_brain_websocket_requires_token_when_auth_is_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_API_TOKEN", "prod-secret")

    with _client(tmp_path) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/brain?since=0"):
                pass

        with client.websocket_connect(
            "/ws/brain?since=0",
            subprotocols=["axiom.auth", "axiom-token.cHJvZC1zZWNyZXQ"],
        ):
            pass
