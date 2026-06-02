from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import axiom.studio.server as server
from axiom import cli
from axiom.schema.models import Base, Source
from axiom.studio.server import create_app


def _make_db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'live.db'}"


def _create_schema(db_url: str) -> None:
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    # P0-5: foreign_keys are now enforced, so the live-synthetic ingest path
    # requires the referenced sources row to exist before entities reference it.
    # Seed it here as a valid precondition. (Deferred: production code should
    # auto-seed this 'live-synthetic' source row — see notes.)
    with Session(engine, future=True) as session:
        if session.get(Source, "live-synthetic") is None:
            session.add(
                Source(
                    id="live-synthetic",
                    source_type="synthetic",
                    display_name="Live Synthetic",
                    connected=True,
                    metadata_json={},
                )
            )
            session.commit()
    engine.dispose()


def test_serve_live_flag_wires_server_config(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_app(**kwargs: Any) -> FastAPI:
        captured.update(kwargs)
        return FastAPI()

    def fake_run(app: FastAPI, **kwargs: Any) -> None:
        captured["app"] = app
        captured["uvicorn"] = kwargs

    db_url = _make_db_url(tmp_path)
    monkeypatch.setattr(server, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "axiom",
            "serve",
            "--db-url",
            db_url,
            "--live",
            "--rate",
            "2.5",
            "--pause-after",
            "7",
        ],
    )

    cli.main()

    assert captured["db_url"] == db_url
    assert captured["live"] is True
    assert captured["live_rate"] == 2.5
    assert captured["live_pause_after"] == 7
    assert captured["uvicorn"]["host"] == "127.0.0.1"


def test_health_reports_live_mode_and_events_emitted(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    _create_schema(db_url)
    app = create_app(db_url=db_url, live=True, live_rate=1000.0, live_pause_after=1)

    with TestClient(app) as client:
        response = client.get("/api/health")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["live"] is True
    assert isinstance(payload["events_emitted"], int)
    assert "current_seq" in payload


def test_live_shutdown_cancels_background_task_promptly(tmp_path: Path) -> None:
    db_url = _make_db_url(tmp_path)
    _create_schema(db_url)
    app = create_app(db_url=db_url, live=True, live_rate=0.001)

    with TestClient(app):
        task = app.state.live_task
        assert task is not None
        assert task.done() is False

    assert task.done() is True
    assert app.state.live_source.task is None
