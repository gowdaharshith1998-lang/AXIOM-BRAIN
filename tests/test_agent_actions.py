from __future__ import annotations

import asyncio
import random

from axiom.govern.agent_actions import demo_action_payload
from axiom.govern.policy_evaluator import DemoPolicyEvaluator
from axiom.organize.clusters import CLUSTER_IDS


def test_policy_evaluator_allows_by_default_with_zero_deny_rate() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0, rng=random.Random(1))
    decision = evaluator.evaluate("engineering_code", "read")
    assert decision.decision == "allow"
    assert decision.policy_id == "AEGIS-1"


def test_policy_evaluator_denies_for_billing_writes() -> None:
    evaluator = DemoPolicyEvaluator(deny_rate=0, rng=random.Random(1))
    decision = evaluator.evaluate("billing_payments", "write")
    assert decision.decision == "deny"
    assert "billing" in decision.reason or decision.reason


def test_demo_action_payload_contains_demo_contract() -> None:
    payload = demo_action_payload(random.Random(2))
    assert str(payload["action_id"]).startswith("act_")
    assert payload["cluster_id"] in CLUSTER_IDS
    assert str(payload["skill_called"]).startswith("skills.")


def test_agent_action_payload_is_async_safe() -> None:
    async def run() -> dict[str, object]:
        await asyncio.sleep(0)
        return demo_action_payload(random.Random(3))

    assert asyncio.run(run())["agent_name"] in {"claude", "cursor", "gpt-5"}
