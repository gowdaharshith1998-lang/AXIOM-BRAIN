from __future__ import annotations

from datetime import datetime
from typing import Any

import uuid_utils as uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
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
    guidance: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_alternative: Mapped[str | None] = mapped_column(String, nullable=True)
    signing_scheme: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    this_hash: Mapped[str] = mapped_column(String, nullable=False)
    reserved_state: Mapped[str | None] = mapped_column("cali" "bra_state", String, nullable=True)
    demo_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


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

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    skill_id: Mapped[str] = mapped_column(String(256), index=True)
    version: Mapped[int] = mapped_column(index=True)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    skill_hash: Mapped[str] = mapped_column(String(128), index=True)
    process_entity_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("entities.id"), index=True
    )
    emitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    signed_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(String, default="")


Index("ix_edges_src_rel", Edge.source_id, Edge.relationship)
Index("ix_edges_tgt_rel", Edge.target_id, Edge.relationship)
Index("ix_entities_type_created", Entity.type, Entity.created_at)
