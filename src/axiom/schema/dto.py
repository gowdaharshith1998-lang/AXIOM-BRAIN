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
    cluster_id: str | None = None
    composite_importance: float = 0.0


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
    action_id: str
    agent_name: str
    intent: str
    target_entity_id: str | None = None
    cluster_id: str | None = None
    decision: str
    reason: str
    policy_id: str
    passport_id: str | None = None
    guidance: str | None = None
    suggested_alternative: str | None = None
    signing_scheme: str
    signature: str
    prev_hash: str | None = None
    this_hash: str
    demo_flag: bool
    created_at: datetime


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
    name: str
    description: str
    intent: str
    trigger_type: str
    trigger_config: dict[str, Any]
    prompt_template: str
    output_schema: dict[str, Any]
    llm_provider: str
    llm_model: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    total_runs: int
