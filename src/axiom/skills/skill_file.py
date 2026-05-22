"""SkillFile primitive — dataclasses for the executable YAML workflow file.

This is categorically different from ``axiom.skills.runner`` (the Phase 8 LLM-call
wrapper for markdown skills). SkillFiles execute deterministically: every step
either succeeds, pauses, or fails — never "the model says". The two primitives
coexist; nothing in ``axiom.skills.runner`` / ``emitter`` / ``registry`` /
``skill_md`` / ``interfaces`` is touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class TriggerMatcher:
    """One entry in ``when_triggered_by`` — matches an inbound intent."""

    intent: str
    source: list[str] | None = None


@dataclass(frozen=True)
class StepIfThen:
    id: str
    type: Literal["if_then"]
    condition: str
    then: list["Step"]


@dataclass(frozen=True)
class StepFetchEntity:
    id: str
    type: Literal["fetch_entity"]
    query: str
    bind_to: str


@dataclass(frozen=True)
class StepWriteEntity:
    id: str
    type: Literal["write_entity"]
    cluster: str
    entity_type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class StepRequireApproval:
    id: str
    type: Literal["require_approval"]
    role: str
    timeout_seconds: int = 3600


@dataclass(frozen=True)
class StepLogDecision:
    id: str
    type: Literal["log_decision"]
    cluster: str
    note: str


Step = (
    StepIfThen
    | StepFetchEntity
    | StepWriteEntity
    | StepRequireApproval
    | StepLogDecision
)


@dataclass(frozen=True)
class SkillFile:
    name: str
    description: str
    version: int
    when_triggered_by: list[TriggerMatcher]
    steps: list[Step]


@dataclass(frozen=True)
class StepResult:
    step_id: str
    step_type: str
    status: Literal["executed", "skipped", "paused", "failed"]
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillFileRun:
    skill_file_name: str
    status: Literal["success", "paused", "failed"]
    step_results: list[StepResult]
    approval_id: str | None = None
    final_receipt_id: str | None = None
    error: str | None = None
