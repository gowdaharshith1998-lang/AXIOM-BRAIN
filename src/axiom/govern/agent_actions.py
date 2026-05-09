from __future__ import annotations

import asyncio
import random
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.ledger import demo_receipt
from axiom.govern.policy_evaluator import (
    RISKY_INTENTS,
    DemoPolicyEvaluator,
)
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.organize.clusters import CLUSTER_IDS

AGENTS = ("claude", "cursor", "gpt-5")
SAFE_INTENTS = ("read", "write", "execute")
ALL_INTENTS = (*SAFE_INTENTS, *sorted(RISKY_INTENTS))


def _now() -> str:
    return datetime.utcnow().isoformat()


def demo_action_payload(
    rng: random.Random | None = None,
    *,
    force_risky: bool = False,
    target_entity_id: str | None = None,
    target_importance: float | None = None,
) -> dict[str, object]:
    source = rng or random.Random()
    cluster = source.choice(CLUSTER_IDS)
    if force_risky:
        intent = source.choice(sorted(RISKY_INTENTS))
    else:
        intent = source.choice(SAFE_INTENTS)
    payload: dict[str, object] = {
        "action_id": f"act_{uuid4().hex[:12]}",
        "agent_name": source.choice(AGENTS),
        "cluster_id": cluster,
        "intent": intent,
        "skill_called": f"skills.{cluster}.lookup",
        "timestamp": _now(),
        "demo": True,
    }
    if target_entity_id is not None:
        payload["target_entity_id"] = target_entity_id
    if target_importance is not None:
        payload["target_importance"] = target_importance
    return payload


def _pick_high_importance_entity(
    session_factory: sessionmaker[Session] | None,
) -> tuple[str | None, float | None, str | None]:
    """Pick a random high-importance entity from the DB.

    Returns (entity_id, importance, another_entity_id_for_alternative).
    """
    if session_factory is None:
        return None, None, None
    try:
        from sqlalchemy import select as sa_select

        from axiom.schema.models import Entity

        session = session_factory()
        try:
            entities = session.execute(sa_select(Entity)).scalars().all()
            from axiom.govern.policy_evaluator import CORRECT_IMPORTANCE_THRESHOLD
            high = [e for e in entities if (e.composite_importance or 0) >= CORRECT_IMPORTANCE_THRESHOLD]
            if not high:
                return None, None, None
            chosen = random.choice(high)
            others = [e for e in entities if e.id != chosen.id]
            alt = random.choice(others).id if others else None
            return chosen.id, chosen.composite_importance or 0.0, alt
        finally:
            session.close()
    except Exception:  # noqa: BLE001
        return None, None, None


async def emit_demo_agent_actions(
    broadcaster: EventBroadcaster,
    *,
    evaluator: DemoPolicyEvaluator | None = None,
    rng: random.Random | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> None:
    source = rng or random.Random()
    policy = evaluator or DemoPolicyEvaluator(rng=source)
    receipt_index = 0
    action_count = 0
    while True:
        await asyncio.sleep(source.uniform(4, 8))
        action_count += 1

        target_entity_id: str | None = None
        target_importance: float | None = None
        suggested_alt: str | None = None
        force_risky = False

        if action_count % 6 in (0, 3):
            eid, imp, alt = _pick_high_importance_entity(session_factory)
            if eid and imp is not None:
                target_entity_id = eid
                target_importance = imp
                force_risky = True
                suggested_alt = alt

        payload = demo_action_payload(
            source,
            force_risky=force_risky,
            target_entity_id=target_entity_id,
            target_importance=target_importance,
        )
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
        decision = policy.evaluate(
            str(payload["cluster_id"]),
            str(payload["intent"]),
            entity_importance=target_importance,
            suggested_alternative=suggested_alt,
        )
        eval_payload: dict[str, object] = {
            **payload,
            "decision": decision.decision,
            "reason": decision.reason,
            "policy_id": decision.policy_id,
            "timestamp": _now(),
        }
        if decision.decision == "correct":
            eval_payload["guidance"] = decision.guidance
            eval_payload["suggested_alternative"] = decision.suggested_alternative
        await broadcaster.publish(
            {
                "type": "agent_action_evaluated",
                "source_id": None,
                "persisted_id": payload["action_id"],
                "payload": eval_payload,
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
