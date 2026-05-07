from __future__ import annotations

import random

from axiom.govern.ledger import synthetic_receipt
from axiom.govern.warden import build_insight_payload


def test_synthetic_receipt_has_hash_and_root() -> None:
    receipt = synthetic_receipt(action_id="act_1", decision="allow", agent_name="claude", index=1)
    assert len(str(receipt["receipt_id"])) == 64
    assert len(str(receipt["merkle_root"])) == 64


def test_synthetic_receipt_root_changes_every_window() -> None:
    first = synthetic_receipt(action_id="act_1", decision="allow", agent_name="claude", index=1)
    later = synthetic_receipt(action_id="act_1", decision="allow", agent_name="claude", index=11)
    assert first["merkle_root"] != later["merkle_root"]


def test_warden_insight_payload_links_entities() -> None:
    payload = build_insight_payload(["a", "b", "c", "d"], random.Random(1))
    assert payload["related_entity_ids"] == ["a", "b", "c"]
    assert 0.65 <= float(payload["confidence"]) <= 0.95


def test_warden_insight_payload_has_recommended_actions() -> None:
    payload = build_insight_payload([], random.Random(2))
    assert payload["recommended_actions"]
    assert str(payload["insight_id"]).startswith("ins_")


def test_synthetic_receipt_is_deterministic_for_same_inputs() -> None:
    first = synthetic_receipt(action_id="act_2", decision="deny", agent_name="cursor", index=4)
    second = synthetic_receipt(action_id="act_2", decision="deny", agent_name="cursor", index=4)
    assert first["receipt_id"] == second["receipt_id"]


def test_warden_insight_limits_related_entities_to_three() -> None:
    payload = build_insight_payload(["a", "b", "c", "d", "e"], random.Random(3))
    assert len(payload["related_entity_ids"]) == 3
