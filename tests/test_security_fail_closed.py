"""Phase 1 regression tests: fail-closed security defaults.

Covers:
  - P0-1 / GOV-PASS-002: the literal ``demo_passport`` master token is
    rejected in production.
  - P0-1 / AUTHZ-001: the wildcard system passport is only bootstrapped in
    explicit demo mode (never in production).
  - P1-1 / GOV-POL-006: policy load failure in production is fatal (fail-closed)
    instead of silently falling back to the allow-all demo evaluator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.passports import (
    SYSTEM_PASSPORT_TOKEN,
    PassportError,
    should_bootstrap_system_passport,
    verify_passport,
)
from axiom.govern.policy_evaluator import DemoPolicyEvaluator, get_policy_evaluator
from axiom.policy import load_policies
from axiom.schema.models import Base


def _sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'sec.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def test_demo_passport_rejected_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AXIOM_ENV", "production")
    sf = _sf(tmp_path)
    with pytest.raises(PassportError, match="invalid_or_missing_passport"):
        verify_passport(sf, SYSTEM_PASSPORT_TOKEN)


def test_system_passport_not_bootstrapped_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AXIOM_ENV", "production")
    monkeypatch.setenv("AXIOM_DEMO", "1")
    monkeypatch.setenv("AXIOM_MCP_ALLOW_SYSTEM_PASSPORT", "1")
    assert should_bootstrap_system_passport() is False


def test_system_passport_bootstrapped_only_in_explicit_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AXIOM_ENV", raising=False)
    monkeypatch.delenv("AXIOM_DEMO", raising=False)
    monkeypatch.delenv("AXIOM_MCP_ALLOW_SYSTEM_PASSPORT", raising=False)
    assert should_bootstrap_system_passport() is False

    monkeypatch.setenv("AXIOM_DEMO", "1")
    assert should_bootstrap_system_passport() is True


def test_policy_fail_closed_in_production_on_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point at an invalid policy so load_policies() raises, then assert the
    # production path refuses to start instead of returning the allow-all demo.
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "invalid.yaml").write_text("rules:\n  - rule_id:", encoding="utf-8")
    monkeypatch.setenv("AXIOM_POLICY_DIR", str(policy_dir))
    monkeypatch.setenv("AXIOM_ENV", "production")
    load_policies.cache_clear()

    try:
        with pytest.raises(SystemExit):
            get_policy_evaluator(_sf(tmp_path))
    finally:
        load_policies.cache_clear()


def test_policy_demo_fallback_outside_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "invalid.yaml").write_text("rules:\n  - rule_id:", encoding="utf-8")
    monkeypatch.setenv("AXIOM_POLICY_DIR", str(policy_dir))
    monkeypatch.delenv("AXIOM_ENV", raising=False)
    load_policies.cache_clear()

    try:
        evaluator = get_policy_evaluator(_sf(tmp_path))
        assert isinstance(evaluator, DemoPolicyEvaluator)
    finally:
        load_policies.cache_clear()
