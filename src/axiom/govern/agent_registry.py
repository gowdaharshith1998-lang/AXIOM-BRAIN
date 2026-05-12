from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import Engine, desc, func, inspect, select
from sqlalchemy.orm import Session

from axiom.schema.models import AgentRegistry, Receipt
from axiom.storage.db import create_schema_table

AgentType = Literal["internal", "external_mcp"]
DECISIONS = {"allow", "correct", "deny"}


def classify_agent_type(agent_name: str) -> AgentType:
    return "internal" if agent_name == "organizer" else "external_mcp"


def ensure_agent_registry_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("agent_registry"):
        create_schema_table(AgentRegistry.__table__, engine)


def agent_registry_row(row: AgentRegistry) -> dict[str, Any]:
    return {
        "agent_name": row.agent_name,
        "first_seen": row.first_seen.isoformat(),
        "last_seen": row.last_seen.isoformat(),
        "total_actions": row.total_actions,
        "allow_count": row.allow_count,
        "correct_count": row.correct_count,
        "deny_count": row.deny_count,
        "last_intent": row.last_intent,
        "last_action_id": row.last_action_id,
        "agent_type": row.agent_type,
        "demo_flag": row.demo_flag,
    }


def upsert_agent_observation(
    session: Session,
    *,
    agent_name: str,
    decision: str,
    intent: str,
    action_id: str,
    observed_at: datetime | None = None,
    demo_flag: bool = True,
) -> AgentRegistry:
    observed_at = observed_at or datetime.utcnow()
    normalized_agent = agent_name.strip() or "external_mcp_client"
    normalized_decision = decision.strip().lower()
    row = session.get(AgentRegistry, normalized_agent)
    if row is None:
        row = AgentRegistry(
            agent_name=normalized_agent,
            first_seen=observed_at,
            last_seen=observed_at,
            agent_type=classify_agent_type(normalized_agent),
            demo_flag=demo_flag,
        )

    row.last_seen = max(row.last_seen or observed_at, observed_at)
    row.first_seen = min(row.first_seen or observed_at, observed_at)
    row.total_actions = int(row.total_actions or 0) + 1
    if normalized_decision == "allow":
        row.allow_count = int(row.allow_count or 0) + 1
    elif normalized_decision == "correct":
        row.correct_count = int(row.correct_count or 0) + 1
    elif normalized_decision == "deny":
        row.deny_count = int(row.deny_count or 0) + 1
    row.last_intent = intent
    row.last_action_id = action_id
    row.agent_type = classify_agent_type(normalized_agent)
    row.demo_flag = bool(row.demo_flag) and demo_flag
    session.add(row)
    return row


def backfill_agent_registry_from_receipts(session: Session) -> int:
    existing = int(session.execute(select(func.count(AgentRegistry.agent_name))).scalar_one())
    if existing > 0:
        return 0

    rows = session.execute(select(Receipt).order_by(Receipt.created_at, Receipt.id)).scalars().all()
    for receipt in rows:
        upsert_agent_observation(
            session,
            agent_name=receipt.agent_name,
            decision=receipt.decision,
            intent=receipt.intent,
            action_id=receipt.action_id,
            observed_at=receipt.created_at,
            demo_flag=receipt.demo_flag,
        )
    session.commit()
    return len(rows)


def get_agents(
    session: Session,
    *,
    days: int = 30,
    agent_type: AgentType | None = None,
) -> list[AgentRegistry]:
    bounded_days = max(1, min(days, 365))
    since = datetime.utcnow() - timedelta(days=bounded_days)
    query = select(AgentRegistry).where(AgentRegistry.last_seen >= since)
    if agent_type is not None:
        query = query.where(AgentRegistry.agent_type == agent_type)
    return list(
        session.execute(query.order_by(desc(AgentRegistry.last_seen), AgentRegistry.agent_name))
        .scalars()
        .all()
    )
