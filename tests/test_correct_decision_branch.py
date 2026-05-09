"""Tests for the CORRECT decision branch in DemoPolicyEvaluator."""
from __future__ import annotations

import random

from axiom.govern.policy_evaluator import (
    CORRECT_IMPORTANCE_THRESHOLD,
    RISKY_INTENTS,
    DemoPolicyEvaluator,
)


def test_high_importance_risky_intent_triggers_correct() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0.15, rng=random.Random(1), vault_unlocked=True)
    decision = evaluator.evaluate(
        "company_knowledge",
        "delete",
        entity_importance=0.50,
        suggested_alternative="ent_alt",
    )
    assert decision.decision == "correct"
    assert decision.guidance != ""
    assert decision.suggested_alternative == "ent_alt"


def test_low_importance_risky_intent_no_correct() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0, rng=random.Random(1), vault_unlocked=True)
    decision = evaluator.evaluate(
        "company_knowledge",
        "delete",
        entity_importance=0.30,
    )
    assert decision.decision != "correct"


def test_high_importance_safe_intent_no_correct() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0, rng=random.Random(1), vault_unlocked=True)
    decision = evaluator.evaluate(
        "company_knowledge",
        "read",
        entity_importance=0.50,
    )
    assert decision.decision == "allow"


def test_vault_locked_no_correct() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0, rng=random.Random(1), vault_unlocked=False)
    decision = evaluator.evaluate(
        "company_knowledge",
        "delete",
        entity_importance=0.50,
    )
    assert decision.decision != "correct"


def test_correct_does_not_break_existing_allow_deny() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0.15, rng=random.Random(42), vault_unlocked=True)
    decisions = []
    for _ in range(50):
        d = evaluator.evaluate("engineering_code", "read")
        decisions.append(d.decision)
    assert "allow" in decisions
    assert "deny" in decisions
    assert "correct" not in decisions


def test_billing_write_still_denies_even_with_high_importance() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0, rng=random.Random(1), vault_unlocked=True)
    decision = evaluator.evaluate(
        "billing_payments",
        "write",
        entity_importance=0.50,
    )
    # write on billing is force-deny, but importance+risky intent check happens first
    # "write" is NOT in RISKY_INTENTS, so CORRECT shouldn't trigger
    assert decision.decision == "deny"


def test_all_risky_intents_trigger_correct() -> None:
    for intent in sorted(RISKY_INTENTS):
        evaluator = DemoPolicyEvaluator(deny_rate=0, rng=random.Random(1), vault_unlocked=True)
        decision = evaluator.evaluate(
            "company_knowledge",
            intent,
            entity_importance=CORRECT_IMPORTANCE_THRESHOLD,
        )
        assert decision.decision == "correct", f"Expected CORRECT for intent={intent}"
