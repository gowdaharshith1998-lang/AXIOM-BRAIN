from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from axiom.schema.models import Base


def _make_app(tmp_path: Path, monkeypatch: Any):
    from axiom.studio.server import create_app

    for key in (
        "AXIOM_CONNECTOR_GITHUB_ENABLED",
        "AXIOM_GITHUB_CLIENT_ID",
        "AXIOM_GITHUB_CLIENT_SECRET",
        "AXIOM_GITHUB_REDIRECT_URI",
    ):
        monkeypatch.delenv(key, raising=False)
    db_url = f"sqlite:///{tmp_path / 'connectors_config.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    return create_app(db_url=db_url, enable_organizer=False)


def test_connector_status_reports_setup_required_without_hidden_feature_flag(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    app = _make_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        status = client.get("/api/internal/connectors/status")
        install = client.post("/api/internal/connectors/github/install")

    assert status.status_code == 200
    github = next(row for row in status.json()["connectors"] if row["vendor"] == "github")
    assert github["configured"] is False
    assert install.status_code == 409
    assert install.json()["detail"] == "GitHub connector setup required"


def test_connector_config_put_enables_real_oauth_install(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    app = _make_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        saved = client.put(
            "/api/internal/connectors/github/config",
            json={
                "oauth_client_id": "github-client",
                "oauth_client_secret": "github-secret",
                "redirect_uri": "http://localhost:5173/api/internal/connectors/github/callback",
                "webhook_secret": "webhook-secret",
            },
        )
        install = client.post("/api/internal/connectors/github/install")

    assert saved.status_code == 200
    assert saved.json()["configured"] is True
    assert install.status_code == 200
    authorize_url = install.json()["authorize_url"]
    assert authorize_url.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=github-client" in authorize_url
    assert "state=" in authorize_url
