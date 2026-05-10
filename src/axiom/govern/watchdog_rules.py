from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from axiom.retrieval.embeddings import cosine_similarity, vector_from_blob
from axiom.schema.models import Edge, Entity, EntityEmbedding


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    rule_id: str
    severity: str
    reason: str
    evidence: dict[str, Any]
    suggested_action: str


WatchdogRule = Callable[[Session, Entity, datetime], AlertCandidate | None]


def _text(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _entity_title(entity: Entity) -> str:
    data = entity.data or {}
    for key in ("title", "name", "subject", "label"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity.id


def _data_text(entity: Entity) -> str:
    data = entity.data or {}
    fragments = [entity.type, entity.cluster_id or ""]
    for value in data.values():
        if isinstance(value, str):
            fragments.append(value)
        elif isinstance(value, (int, float, bool)):
            fragments.append(str(value))
        elif isinstance(value, list):
            fragments.extend(str(item) for item in value if isinstance(item, (str, int, float)))
    return " ".join(fragments).lower()


def _is_decision(entity: Entity) -> bool:
    return (
        entity.type.lower() == "decision"
        or _text((entity.data or {}).get("doc_type")) == "decision"
    )


def _is_policy(entity: Entity) -> bool:
    data = entity.data or {}
    return (
        entity.type.lower() in {"policy", "governance"}
        or _text(data.get("doc_type")) == "policy"
        or _text(data.get("kind")) == "policy"
        or (entity.cluster_id or "").lower() == "decisions_policy"
        or "policy" in _data_text(entity)
    )


def _is_runbook(entity: Entity) -> bool:
    data = entity.data or {}
    return (
        entity.type.lower() == "runbook"
        or _text(data.get("doc_type")) == "runbook"
        or _text(data.get("kind")) == "runbook"
        or "runbook" in _data_text(entity)
    )


def _is_incident_ops(entity: Entity) -> bool:
    haystack = _data_text(entity)
    return (
        (entity.cluster_id or "").lower() in {"incident_ops", "incidents_ops"}
        or "incident" in haystack
    )


def _edge_other_id(edge: Edge, entity_id: str) -> str:
    return edge.target_id if edge.source_id == entity_id else edge.source_id


def _edges_for_entity(session: Session, entity_id: str) -> list[Edge]:
    return (
        session.execute(
            select(Edge).where(or_(Edge.source_id == entity_id, Edge.target_id == entity_id))
        )
        .scalars()
        .all()
    )


def _recent_linked_decision_ids(
    session: Session,
    entity: Entity,
    *,
    since: datetime,
) -> list[str]:
    ids: list[str] = []
    for edge in _edges_for_entity(session, entity.id):
        if edge.created_at < since:
            continue
        other = session.get(Entity, _edge_other_id(edge, entity.id))
        if other is not None and _is_decision(other):
            ids.append(other.id)
    data = entity.data or {}
    linked = data.get("decision_id") or data.get("linked_decision_id")
    if isinstance(linked, str) and linked:
        decision = session.get(Entity, linked)
        if decision is not None and _is_decision(decision) and decision.updated_at >= since:
            ids.append(decision.id)
    return sorted(set(ids))


def billing_change_without_decision(
    session: Session,
    entity: Entity,
    now: datetime,
) -> AlertCandidate | None:
    if (entity.cluster_id or "").lower() != "billing_payments":
        return None
    linked = _recent_linked_decision_ids(session, entity, since=now - timedelta(days=7))
    if linked:
        return None
    return AlertCandidate(
        rule_id="R1",
        severity="warning",
        reason=(
            f"{_entity_title(entity)} touches billing_payments without a linked decision "
            "in 7 days."
        ),
        evidence={
            "entity_id": entity.id,
            "cluster_id": entity.cluster_id,
            "recent_decision_ids": linked,
            "window_days": 7,
        },
        suggested_action=(
            "Link the billing change to a current decision or create a decision record."
        ),
    )


def ticket_severity_mismatch_runbook(
    session: Session,
    entity: Entity,
    _now: datetime,
) -> AlertCandidate | None:
    data = entity.data or {}
    priority = _text(data.get("priority") or data.get("severity"))
    if entity.type.lower() != "ticket" or priority not in {"p0", "p1", "sev1", "critical"}:
        return None

    linked_runbooks: list[str] = []
    for edge in _edges_for_entity(session, entity.id):
        other = session.get(Entity, _edge_other_id(edge, entity.id))
        if other is not None and _is_runbook(other) and _is_incident_ops(other):
            linked_runbooks.append(other.id)
    if linked_runbooks:
        return None

    return AlertCandidate(
        rule_id="R2",
        severity="critical",
        reason=f"{_entity_title(entity)} is P1 but has no incident_ops runbook edge.",
        evidence={
            "entity_id": entity.id,
            "priority": priority,
            "incident_runbook_ids": linked_runbooks,
        },
        suggested_action="Attach the relevant incident operations runbook before escalation.",
    )


def policy_doc_orphaned(
    session: Session,
    entity: Entity,
    now: datetime,
) -> AlertCandidate | None:
    if not _is_policy(entity) or entity.created_at > now - timedelta(days=30):
        return None
    inbound_count = int(
        session.execute(select(func.count(Edge.id)).where(Edge.target_id == entity.id)).scalar_one()
    )
    if inbound_count > 0:
        return None
    return AlertCandidate(
        rule_id="R3",
        severity="warning",
        reason=f"{_entity_title(entity)} is an older policy document with zero inbound edges.",
        evidence={"entity_id": entity.id, "inbound_edges": inbound_count, "age_days": 30},
        suggested_action="Connect this policy to an owning decision, process, or archive it.",
    )


def _historic_importance(entity: Entity) -> tuple[float | None, str | None]:
    data = entity.data or {}
    for key in (
        "composite_importance_24h_ago",
        "previous_composite_importance",
        "previous_importance",
        "confidence_24h_ago",
    ):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value), key
    history = data.get("importance_history")
    if isinstance(history, list):
        numeric = [
            float(item.get("value"))
            for item in history
            if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
        ]
        if numeric:
            return numeric[0], "importance_history"
    return None, None


def confidence_drift_high(
    _session: Session,
    entity: Entity,
    _now: datetime,
) -> AlertCandidate | None:
    previous, source = _historic_importance(entity)
    if previous is None:
        return None
    current = float(entity.composite_importance or 0.0)
    drop = previous - current
    if drop <= 0.3:
        return None
    return AlertCandidate(
        rule_id="R4",
        severity="warning",
        reason=f"{_entity_title(entity)} confidence drift dropped by {drop:.2f} in 24h.",
        evidence={
            "entity_id": entity.id,
            "previous_composite_importance": previous,
            "current_composite_importance": current,
            "drop": round(drop, 4),
            "source": source,
        },
        suggested_action="Review new edges and recent entity edits that reduced confidence.",
    )


def cluster_outlier(
    session: Session,
    entity: Entity,
    _now: datetime,
) -> AlertCandidate | None:
    if not entity.cluster_id:
        return None
    embedding = session.get(EntityEmbedding, entity.id)
    if embedding is None:
        return None
    peers = (
        session.execute(
            select(EntityEmbedding)
            .join(Entity, Entity.id == EntityEmbedding.entity_id)
            .where(Entity.cluster_id == entity.cluster_id, Entity.id != entity.id)
        )
        .scalars()
        .all()
    )
    if not peers:
        return None
    peer_vectors = [vector_from_blob(row.embedding) for row in peers]
    entity_vector = vector_from_blob(embedding.embedding)
    dimensions = len(entity_vector)
    if dimensions == 0 or any(len(vector) != dimensions for vector in peer_vectors):
        return None
    centroid = [
        sum(vector[index] for vector in peer_vectors) / len(peer_vectors)
        for index in range(dimensions)
    ]
    distance = 1.0 - cosine_similarity(entity_vector, centroid)
    if distance <= 0.5:
        return None
    return AlertCandidate(
        rule_id="R5",
        severity="info",
        reason=f"{_entity_title(entity)} is an embedding outlier in {entity.cluster_id}.",
        evidence={
            "entity_id": entity.id,
            "cluster_id": entity.cluster_id,
            "cosine_distance": round(distance, 4),
            "peer_count": len(peers),
        },
        suggested_action="Review the entity cluster assignment or update neighboring links.",
    )


def stale_decision_referenced(
    session: Session,
    entity: Entity,
    now: datetime,
) -> AlertCandidate | None:
    stale_decisions: list[dict[str, Any]] = []
    cutoff = now - timedelta(days=90)
    for edge in _edges_for_entity(session, entity.id):
        other = session.get(Entity, _edge_other_id(edge, entity.id))
        if other is None or not _is_decision(other) or other.updated_at > cutoff:
            continue
        edge_data = edge.data or {}
        load_bearing = bool(edge_data.get("load_bearing")) or _text(edge.relationship) in {
            "depends_on",
            "blocks",
            "requires",
            "governed_by",
            "load_bearing",
        }
        if load_bearing:
            stale_decisions.append(
                {
                    "decision_id": other.id,
                    "edge_id": edge.id,
                    "decision_updated_at": other.updated_at.isoformat(),
                }
            )
    if not stale_decisions:
        return None
    return AlertCandidate(
        rule_id="R6",
        severity="warning",
        reason=f"{_entity_title(entity)} still depends on a decision older than 90 days.",
        evidence={"entity_id": entity.id, "stale_decisions": stale_decisions},
        suggested_action="Refresh the referenced decision or mark the dependency non-load-bearing.",
    )


DEFAULT_RULES: tuple[WatchdogRule, ...] = (
    billing_change_without_decision,
    ticket_severity_mismatch_runbook,
    policy_doc_orphaned,
    confidence_drift_high,
    cluster_outlier,
    stale_decision_referenced,
)
