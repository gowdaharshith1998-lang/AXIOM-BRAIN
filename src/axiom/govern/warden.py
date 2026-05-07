from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.models import Entity

MESSAGES = (
    "PR-341 modifies billing code without RFC reference",
    "Customer support ticket CS-1182 mentions a pricing exception not documented in decisions",
    "New hire added without onboarding doc updated",
    "Incident runbook RUN-42 hasn't been tested in 90 days",
    "Refund volume up 28% week-over-week - investigate",
)


def build_insight_payload(
    entity_ids: list[str],
    rng: random.Random | None = None,
) -> dict[str, object]:
    source = rng or random.Random()
    return {
        "insight_id": f"ins_{uuid4().hex[:12]}",
        "severity": source.choice(("info", "warning", "critical")),
        "message": source.choice(MESSAGES),
        "confidence": round(source.uniform(0.65, 0.95), 2),
        "related_entity_ids": entity_ids[:3],
        "recommended_actions": ["Open RFC", "Compare incident history", "Notify service owner"],
        "timestamp": datetime.utcnow().isoformat(),
    }


async def emit_warden_insights(
    broadcaster: EventBroadcaster,
    session_factory: sessionmaker[Any],
    *,
    rng: random.Random | None = None,
) -> None:
    source = rng or random.Random()
    while True:
        await asyncio.sleep(source.uniform(30, 90))
        with session_factory() as session:
            ids = list(session.execute(select(Entity.id).limit(12)).scalars())
        payload = build_insight_payload(ids, source)
        await broadcaster.publish(
            {
                "type": "insight_flagged",
                "source_id": None,
                "persisted_id": payload["insight_id"],
                "payload": payload,
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
        )
