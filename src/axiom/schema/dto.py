from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SourceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: str
    display_name: str
    connected: bool
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any]


class EntityDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str  # free-text, not an enum
    data: dict[str, Any]
    source_id: str | None = None
    created_at: datetime
    updated_at: datetime


class EdgeDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    target_id: str
    relationship: str  # free-text, not an enum
    data: dict[str, Any]
    created_at: datetime


class ReceiptDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    receipt_type: str
    merkle_leaf_index: int
    created_at: datetime
    payload: dict[str, Any]
    signature_ed25519_b64: str | None = None
    signature_mldsa_b64: str | None = None


class ActionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    tool: str
    params: dict[str, Any]
    decision: str
    result_hash: str
    task_id: str | None = None
    created_at: datetime


class SkillDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    skill_id: str
    version: int
    scope: str
    skill_hash: str
    process_entity_id: str
    emitted_at: datetime
    signed_metadata: dict[str, Any]
    markdown: str

