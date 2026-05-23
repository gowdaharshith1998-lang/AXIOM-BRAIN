from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.schema.models import Action, Base
from axiom.studio.server import create_app


def _build_db(tmp_path: Path, name: str) -> tuple[str, sessionmaker[Session]]:
    """Create a fresh sqlite DB with the full schema; return (db_url, session factory)."""
    db_url = f"sqlite:///{tmp_path / name}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return db_url, session_factory


def test_activity_endpoint_returns_empty_list_on_fresh_db(tmp_path: Path) -> None:
    """Fresh DB: endpoint returns 200 with items=[] (not 500, not 404)."""
    db_url, _ = _build_db(tmp_path, "activity_empty.db")
    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/internal/agents/activity")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["items"] == []


def test_activity_endpoint_excludes_watchdog_actions(tmp_path: Path) -> None:
    """Watchdog-derived tool calls must not surface in the runtime feed."""
    db_url, session_factory = _build_db(tmp_path, "activity_watchdog.db")
    with session_factory() as session:
        session.add(
            Action(
                id="act_watchdog",
                agent_id="warden",
                tool="watchdog_sweep",
                params={},
                decision="allow",
                result_hash="hash_watchdog",
            )
        )
        session.add(
            Action(
                id="act_normal",
                agent_id="claude",
                tool="search_entities",
                params={},
                decision="allow",
                result_hash="hash_normal",
            )
        )
        session.commit()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/internal/agents/activity")

    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert "watchdog" not in item.get("title", "").lower()
        assert "watchdog" not in (item.get("agent_name") or "").lower()
    # the non-watchdog tool call is still surfaced
    assert any("search_entities" in item["title"] for item in data["items"])


def test_activity_endpoint_limit_param_works(tmp_path: Path) -> None:
    """The limit query param caps the number of returned rows."""
    db_url, session_factory = _build_db(tmp_path, "activity_limit.db")
    with session_factory() as session:
        for index in range(12):
            session.add(
                Action(
                    id=f"act_{index}",
                    agent_id="claude",
                    tool=f"tool_{index}",
                    params={},
                    decision="allow",
                    result_hash=f"hash_{index}",
                )
            )
        session.commit()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        response = client.get("/api/internal/agents/activity?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 5
