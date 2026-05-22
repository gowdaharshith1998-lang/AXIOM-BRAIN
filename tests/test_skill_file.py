"""Tests for the SkillFile primitive — parser, runner, and store.

Tests assert observable behaviour (status strings, receipt/approval counts,
resolved note text), never internal implementation details. The runner/store
take a real ``sessionmaker`` bound to a file-based SQLite DB so the governance
primitives (``chain_insert_receipt``, ``create_approval_request``) — which
require a ``sessionmaker`` — work exactly as in production.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.schema.models import ApprovalRequest, Base, Entity, Receipt

REFUND_YAML = """\
name: handle_refund_request
description: How our company processes refund requests
version: 1
when_triggered_by:
  - intent: refund
    source: [slack, gmail, linear]
steps:
  - id: check_amount
    type: if_then
    condition: trigger.payload.amount > 500
    then:
      - id: require_vp_approval
        type: require_approval
        role: vp_support
        timeout_seconds: 1800
  - id: fetch_customer
    type: fetch_entity
    query: "customer:{trigger.payload.customer_id}"
    bind_to: customer
  - id: log_decision
    type: log_decision
    cluster: billing
    note: "Refund {customer.name}: ${trigger.payload.amount}"
"""

WRITE_ENTITY_YAML = """\
name: record_refund_note
description: persists a refund note entity
version: 1
when_triggered_by:
  - intent: refund
steps:
  - id: save_note
    type: write_entity
    cluster: billing
    entity_type: refund_note
    data:
      customer_id: "{trigger.payload.customer_id}"
      amount: 999
"""


@pytest.fixture
def session_factory(tmp_path):
    """A real sessionmaker bound to a per-test file-based SQLite DB."""
    engine = create_engine(f"sqlite:///{tmp_path}/skill_test.db", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _seed_customer(session_factory, entity_id: str, name: str) -> None:
    """Insert a customer Entity with a known id (Entity.id is settable)."""
    with session_factory() as session:
        session.add(
            Entity(id=entity_id, type="customer", data={"name": name}, cluster_id="customers")
        )
        session.commit()


# ── Parser ────────────────────────────────────────────────────────────────


def test_parser_roundtrip_refund_example():
    from axiom.skills.skill_file_parser import parse_skill_file_yaml

    sf = parse_skill_file_yaml(REFUND_YAML)
    assert sf.name == "handle_refund_request"
    assert sf.version == 1
    assert len(sf.steps) == 3
    assert sf.steps[0].type == "if_then"
    assert len(sf.steps[0].then) == 1
    assert sf.steps[0].then[0].type == "require_approval"
    assert sf.steps[0].then[0].role == "vp_support"
    assert sf.steps[0].then[0].timeout_seconds == 1800
    assert sf.when_triggered_by[0].intent == "refund"
    assert sf.when_triggered_by[0].source == ["slack", "gmail", "linear"]


def test_parser_rejects_unknown_step_type():
    from axiom.skills.skill_file_parser import SkillFileParseError, parse_skill_file_yaml

    bad = REFUND_YAML.replace("type: if_then", "type: not_a_real_step")
    with pytest.raises(SkillFileParseError) as exc:
        parse_skill_file_yaml(bad)
    assert "not_a_real_step" in str(exc.value)


def test_parser_rejects_invalid_yaml():
    from axiom.skills.skill_file_parser import SkillFileParseError, parse_skill_file_yaml

    with pytest.raises(SkillFileParseError):
        parse_skill_file_yaml("name: [unclosed")


# ── Runner ────────────────────────────────────────────────────────────────


def test_runner_executes_fetch_and_log_end_to_end(session_factory):
    from axiom.skills.skill_file_parser import parse_skill_file_yaml
    from axiom.skills.skill_file_runner import SkillFileRunner

    _seed_customer(session_factory, "cust_acme_001", "Acme Corp")

    sf = parse_skill_file_yaml(REFUND_YAML)
    runner = SkillFileRunner(session_factory=session_factory)
    result = runner.run(
        sf,
        trigger={
            "intent": "refund",
            "source": "slack",
            "payload": {"amount": 120, "customer_id": "cust_acme_001"},
        },
    )
    assert result.status == "success"
    executed = [r for r in result.step_results if r.status == "executed"]
    assert len(executed) == 2  # fetch + log_decision (if_then false → skipped)

    # EARS: the low-amount path chains 2 receipts (fetch_entity + log_decision).
    with session_factory() as session:
        assert session.query(Receipt).count() == 2


def test_runner_pauses_on_require_approval(session_factory):
    from axiom.skills.skill_file_parser import parse_skill_file_yaml
    from axiom.skills.skill_file_runner import SkillFileRunner

    _seed_customer(session_factory, "cust_acme_001", "Acme Corp")

    sf = parse_skill_file_yaml(REFUND_YAML)
    runner = SkillFileRunner(session_factory=session_factory)
    result = runner.run(
        sf,
        trigger={
            "intent": "refund",
            "source": "slack",
            "payload": {"amount": 750, "customer_id": "cust_acme_001"},
        },
    )
    assert result.status == "paused"
    assert result.approval_id is not None

    with session_factory() as session:
        assert session.query(ApprovalRequest).count() == 1

    paused = [r for r in result.step_results if r.status == "paused"]
    assert len(paused) == 1
    # Execution halted at the approval — fetch/log never ran.
    assert not [r for r in result.step_results if r.status == "executed"]


def test_runner_variable_substitution(session_factory):
    """{trigger.payload.x} and {customer.name} must resolve in query and note."""
    from axiom.skills.skill_file_parser import parse_skill_file_yaml
    from axiom.skills.skill_file_runner import SkillFileRunner

    _seed_customer(session_factory, "cust_xyz_999", "Beta Industries")

    sf = parse_skill_file_yaml(REFUND_YAML)
    runner = SkillFileRunner(session_factory=session_factory)
    result = runner.run(
        sf,
        trigger={
            "intent": "refund",
            "source": "slack",
            "payload": {"amount": 80, "customer_id": "cust_xyz_999"},
        },
    )
    assert result.status == "success"
    log_result = next(
        r
        for r in result.step_results
        if r.step_id == "log_decision" and r.status == "executed"
    )
    assert "Beta Industries" in log_result.detail["resolved_note"]
    assert "$80" in log_result.detail["resolved_note"]


def test_runner_fails_on_missing_entity(session_factory):
    from axiom.skills.skill_file_parser import parse_skill_file_yaml
    from axiom.skills.skill_file_runner import SkillFileRunner

    # No customer seeded — fetch_entity must fail loudly, not return None.
    sf = parse_skill_file_yaml(REFUND_YAML)
    runner = SkillFileRunner(session_factory=session_factory)
    result = runner.run(
        sf,
        trigger={
            "intent": "refund",
            "source": "slack",
            "payload": {"amount": 120, "customer_id": "nonexistent_customer"},
        },
    )
    assert result.status == "failed"
    assert result.error is not None
    failed = [r for r in result.step_results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].step_id == "fetch_customer"


def test_runner_write_entity(session_factory):
    from axiom.skills.skill_file_parser import parse_skill_file_yaml
    from axiom.skills.skill_file_runner import SkillFileRunner
    from axiom.storage.crud import get_entity

    sf = parse_skill_file_yaml(WRITE_ENTITY_YAML)
    runner = SkillFileRunner(session_factory=session_factory)
    result = runner.run(
        sf,
        trigger={"intent": "refund", "payload": {"customer_id": "cust_acme_001"}},
    )
    assert result.status == "success"
    saved = next(r for r in result.step_results if r.step_id == "save_note")
    assert saved.status == "executed"

    new_entity_id = saved.detail["entity_id"]
    with session_factory() as session:
        dto = get_entity(session, new_entity_id)
        assert dto is not None
        assert dto.type == "refund_note"
        assert dto.data["customer_id"] == "cust_acme_001"
        assert dto.data["amount"] == 999


# ── Store ─────────────────────────────────────────────────────────────────


def test_store_save_and_load_roundtrip(session_factory):
    from axiom.skills.skill_file_store import get_skill_file, save_skill_file

    with session_factory() as session:
        saved = save_skill_file(session, "handle_refund_request", REFUND_YAML)
        assert saved.current_version == 1
        assert saved.validation_status == "valid"

        loaded = get_skill_file(session, "handle_refund_request")
        assert loaded is not None
        assert loaded.yaml_text == REFUND_YAML
        assert loaded.description == "How our company processes refund requests"


def test_store_invalid_save_does_not_bump_version(session_factory):
    from axiom.skills.skill_file_store import list_versions, save_skill_file

    with session_factory() as session:
        save_skill_file(session, "handle_refund_request", REFUND_YAML)
        bad = REFUND_YAML.replace("type: if_then", "type: nope")
        result = save_skill_file(session, "handle_refund_request", bad)
        assert result.validation_status == "invalid"
        assert result.current_version == 1  # unchanged — invalid never promoted

        versions = list_versions(session, "handle_refund_request")
        assert len(versions) == 2
        assert versions[0]["validation_status"] == "invalid"
        assert versions[1]["validation_status"] == "valid"

        # A valid save after an invalid one must not collide on version number.
        fixed = save_skill_file(session, "handle_refund_request", REFUND_YAML)
        assert fixed.validation_status == "valid"
        assert fixed.current_version == 3
