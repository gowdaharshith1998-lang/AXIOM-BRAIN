from __future__ import annotations

import asyncio
import random
from datetime import datetime
from uuid import uuid4

from axiom.govern.ledger import demo_receipt
from axiom.govern.policy_evaluator import DemoPolicyEvaluator
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.organize.clusters import CLUSTER_IDS

AGENTS = ("claude", "cursor", "gpt-5")
INTENTS = ("read", "write", "execute")


def _now() -> str:
    return datetime.utcnow().isoformat()


def demo_action_payload(rng: random.Random | None = None) -> dict[str, object]:
    source = rng or random.Random()
    cluster = source.choice(CLUSTER_IDS)
    intent = source.choice(INTENTS)
    return {
        "action_id": f"act_{uuid4().hex[:12]}",
        "agent_name": source.choice(AGENTS),
        "cluster_id": cluster,
        "intent": intent,
        "skill_called": f"skills.{cluster}.lookup",
        "timestamp": _now(),
        "demo": True,
    }


async def emit_demo_agent_actions(
    broadcaster: EventBroadcaster,
    *,
    evaluator: DemoPolicyEvaluator | None = None,
    rng: random.Random | None = None,
) -> None:
    source = rng or random.Random()
    policy = evaluator or DemoPolicyEvaluator(rng=source)
    receipt_index = 0
    while True:
        await asyncio.sleep(source.uniform(4, 8))
        payload = demo_action_payload(source)
        await broadcaster.publish(
            {
                "type": "agent_action",
                "source_id": None,
                "persisted_id": payload["action_id"],
                "payload": payload,
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
        )
        await asyncio.sleep(0.2)
        decision = policy.evaluate(str(payload["cluster_id"]), str(payload["intent"]))
        await broadcaster.publish(
            {
                "type": "agent_action_evaluated",
                "source_id": None,
                "persisted_id": payload["action_id"],
                "payload": {
                    **payload,
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "policy_id": decision.policy_id,
                    "timestamp": _now(),
                },
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
        )
        receipt_index += 1
        await broadcaster.publish(
            {
                "type": "receipt_added",
                "source_id": None,
                "persisted_id": payload["action_id"],
                "payload": demo_receipt(
                    action_id=str(payload["action_id"]),
                    decision=decision.decision,
                    agent_name=str(payload["agent_name"]),
                    index=receipt_index,
                ),
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
        )
