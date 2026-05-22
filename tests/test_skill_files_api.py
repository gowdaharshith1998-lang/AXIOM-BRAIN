"""Tests for the SkillFile REST API endpoints.

Inline TestClient construction (matching the existing API-test pattern in this
repo). ``TestClient(app)`` is used without a ``with`` block so the lifespan —
and therefore the disk seed — does not run; each test starts from an empty
store.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from axiom.schema.models import Base
from axiom.studio.server import create_app

REFUND_YAML = """\
name: handle_refund_request
description: How our company processes refund requests
version: 1
when_triggered_by:
  - intent: refund
    source: [slack]
steps:
  - id: log_decision
    type: log_decision
    cluster: billing
    note: "test note"
"""

LOG_ONLY_YAML = """\
name: log_only_flow
description: a one-step logging workflow
version: 1
when_triggered_by:
  - intent: refund
steps:
  - id: log_it
    type: log_decision
    cluster: billing
    note: "refund of ${trigger.payload.amount}"
"""


def _build_client(tmp_path: Path) -> TestClient:
    db_url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    return TestClient(create_app(db_url=db_url))


def test_list_skill_files_empty(tmp_path: Path):
    client = _build_client(tmp_path)
    response = client.get("/api/internal/skill-files")
    assert response.status_code == 200
    assert response.json() == {"skill_files": []}


def test_put_creates_then_list_returns_one(tmp_path: Path):
    client = _build_client(tmp_path)
    response = client.put(
        "/api/internal/skill-files/handle_refund_request",
        json={"yaml_text": REFUND_YAML},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["validation_status"] == "valid"

    listed = client.get("/api/internal/skill-files").json()["skill_files"]
    assert len(listed) == 1
    assert listed[0]["name"] == "handle_refund_request"
    assert listed[0]["validation_status"] == "valid"


def test_put_invalid_yaml_does_not_bump_version(tmp_path: Path):
    client = _build_client(tmp_path)
    client.put(
        "/api/internal/skill-files/handle_refund_request",
        json={"yaml_text": REFUND_YAML},
    )
    bad = REFUND_YAML.replace("type: log_decision", "type: not_a_step")
    response = client.put(
        "/api/internal/skill-files/handle_refund_request",
        json={"yaml_text": bad},
    )
    body = response.json()
    assert body["validation_status"] == "invalid"
    assert body["version"] == 1  # not bumped
    assert body["validation_errors"]


def test_get_404_when_missing(tmp_path: Path):
    client = _build_client(tmp_path)
    response = client.get("/api/internal/skill-files/does_not_exist")
    assert response.status_code == 404


def test_run_skill_file_returns_success(tmp_path: Path):
    client = _build_client(tmp_path)
    client.put(
        "/api/internal/skill-files/log_only_flow",
        json={"yaml_text": LOG_ONLY_YAML},
    )
    response = client.post(
        "/api/internal/skill-files/log_only_flow/run",
        json={"trigger": {"intent": "refund", "payload": {"amount": 42}}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["steps_executed"] == 1
