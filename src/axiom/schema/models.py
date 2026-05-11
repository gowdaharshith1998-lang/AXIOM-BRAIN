from __future__ import annotations

from datetime import date, datetime
from typing import Any

import uuid_utils as uuid
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    """RFC-9562 UUIDv7: time-ordered, sortable as 32 hex chars."""
    return uuid.uuid7().hex


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(256))
    connected: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(64), index=True)  # free-text; NOT enum
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("sources.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )
    cluster_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, default=None
    )
    composite_importance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, index=True
    )


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("entities.id"), index=True)
    target_id: Mapped[str] = mapped_column(String(32), ForeignKey("entities.id"), index=True)
    relationship: Mapped[str] = mapped_column(String(64), index=True)  # free-text; NOT enum
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class EntityEmbedding(Base):
    __tablename__ = "entity_embeddings"
    __table_args__ = (Index("ix_entity_embeddings_content_hash", "content_hash"),)

    entity_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("entities.id"),
        primary_key=True,
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_receipts_action_id"),
        Index("ix_receipts_created_at_desc", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String, nullable=False)
    target_entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(String, nullable=True)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    policy_id: Mapped[str] = mapped_column(String, nullable=False)
    passport_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("agent_passports.passport_id"), nullable=True, index=True
    )
    guidance: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_alternative: Mapped[str | None] = mapped_column(String, nullable=True)
    signing_scheme: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    this_hash: Mapped[str] = mapped_column(String, nullable=False)
    reserved_state: Mapped[str | None] = mapped_column("cali" "bra_state", String, nullable=True)
    demo_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class MetricsSnapshot(Base):
    __tablename__ = "metrics_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", name="uq_metrics_snapshots_snapshot_date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    allow_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    deny_count: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_count: Mapped[int] = mapped_column(Integer, nullable=False)
    brain_health_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    agent_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    total_actions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deny_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_intent: Mapped[str | None] = mapped_column(String, nullable=True)
    last_action_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    demo_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AgentPassport(Base):
    __tablename__ = "agent_passports"

    passport_id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    agent_class: Mapped[str] = mapped_column(String, nullable=False)
    owner_email: Mapped[str] = mapped_column(String, nullable=False)
    scope_clusters: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    scope_intents: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    scope_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    not_before: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kill_switch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    issuer_signature: Mapped[str] = mapped_column(String, nullable=False)
    signing_scheme: Mapped[str] = mapped_column(String, nullable=False, default="demo")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PassportCredential(Base):
    __tablename__ = "passport_credentials"

    credential_hash: Mapped[str] = mapped_column(String, primary_key=True)
    passport_id: Mapped[str] = mapped_column(
        String, ForeignKey("agent_passports.passport_id"), nullable=False, index=True
    )
    presented_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_presented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ClusterCheckRun(Base):
    __tablename__ = "cluster_check_runs"
    __table_args__ = (
        Index("ix_cluster_check_runs_cluster_run_at", "cluster_id", "run_at"),
        Index("ix_cluster_check_runs_severity_run_at", "severity", "run_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    cluster_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False, default="cluster_health")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_ingest_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False, default="organizer")
    reason: Mapped[str] = mapped_column(String, nullable=False)


class LLMProviderKey(Base):
    __tablename__ = "llm_provider_keys"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    encrypted_key: Mapped[str] = mapped_column(String(8192), nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(4), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_status: Mapped[str] = mapped_column(String(16), nullable=False, default="untested")
    demo_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    tool: Mapped[str] = mapped_column(String(128), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    result_hash: Mapped[str] = mapped_column(String(128))
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skills_status_intent", "status", "intent"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    intent: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt_template: Mapped[str] = mapped_column(String, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SkillRun(Base):
    __tablename__ = "skill_runs"
    __table_args__ = (
        Index("ix_skill_runs_skill_run_at", "skill_id", "run_at"),
        Index("ix_skill_runs_skill_idempotency", "skill_id", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    skill_id: Mapped[str] = mapped_column(String(32), ForeignKey("skills.id"), nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    receipt_id: Mapped[str | None] = mapped_column(String, ForeignKey("receipts.id"), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)


class WatchdogAlert(Base):
    __tablename__ = "watchdog_alerts"
    __table_args__ = (
        Index("ix_watchdog_alerts_status_detected", "status", "detected_at"),
        Index("ix_watchdog_alerts_entity_rule_status", "entity_id", "rule_id", "status"),
    )

    alert_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("entities.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    suggested_action: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    demo_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_status_created", "status", "created_at"),
        Index("ix_approval_requests_required_role_status", "required_role", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    passport_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    intent: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_entity_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    proposed_action: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    policy_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    guidance: Mapped[str | None] = mapped_column(String, nullable=True)
    required_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String, nullable=True)
    resume_token: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)


Index("ix_edges_src_rel", Edge.source_id, Edge.relationship)
Index("ix_edges_tgt_rel", Edge.target_id, Edge.relationship)
Index("ix_entities_type_created", Entity.type, Entity.created_at)
Index("ix_metrics_snapshots_snapshot_date_desc", MetricsSnapshot.snapshot_date.desc())
