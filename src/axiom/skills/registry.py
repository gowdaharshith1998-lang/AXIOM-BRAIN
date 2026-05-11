from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Literal

from sqlalchemy import Engine, desc, inspect, select
from sqlalchemy.orm import Session

from axiom.schema.models import Skill, SkillRun
from axiom.storage.db import get_session

SkillIntent = Literal["classify", "summarize", "extract", "transform", "monitor"]
TriggerType = Literal["manual", "schedule", "event"]
SkillStatus = Literal["draft", "active", "paused", "archived"]

VALID_INTENTS: Final[frozenset[str]] = frozenset(
    {"classify", "summarize", "extract", "transform", "monitor"}
)
VALID_TRIGGER_TYPES: Final[frozenset[str]] = frozenset({"manual", "schedule", "event"})
VALID_STATUSES: Final[frozenset[str]] = frozenset({"draft", "active", "paused", "archived"})


class SkillNotFound(LookupError):  # noqa: N818
    pass


def _validate_choice(value: str, allowed: frozenset[str], label: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise ValueError(f"invalid {label}: {value!r}")
    return normalized


def _validate_trigger_config(trigger_type: str, config: dict[str, Any]) -> None:
    if trigger_type == "manual":
        return
    if trigger_type == "schedule" and (
        "cron" in config or isinstance(config.get("interval_seconds"), int)
    ):
        return
    if trigger_type == "event" and isinstance(config.get("event_type"), str):
        return
    raise ValueError(f"invalid trigger_config for trigger_type={trigger_type!r}")


def skill_to_dict(row: Skill) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "intent": row.intent,
        "trigger_type": row.trigger_type,
        "trigger_config": row.trigger_config or {},
        "prompt_template": row.prompt_template,
        "output_schema": row.output_schema or {},
        "llm_provider": row.llm_provider,
        "llm_model": row.llm_model,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at is not None else None,
        "total_runs": row.total_runs,
    }


def skill_run_to_dict(row: SkillRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "skill_id": row.skill_id,
        "run_at": row.run_at.isoformat(),
        "status": row.status,
        "input_payload": row.input_payload or {},
        "output_payload": row.output_payload,
        "receipt_id": row.receipt_id,
        "error_message": row.error_message,
        "duration_ms": row.duration_ms,
        "agent_name": row.agent_name,
    }


def ensure_skills_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.has_table("skills"):
        columns = {column["name"] for column in inspector.get_columns("skills")}
        expected = {
            "id",
            "name",
            "description",
            "intent",
            "trigger_type",
            "trigger_config",
            "prompt_template",
            "output_schema",
            "llm_provider",
            "llm_model",
            "status",
            "created_by",
            "created_at",
            "updated_at",
            "last_run_at",
            "total_runs",
        }
        if not expected.issubset(columns):
            with engine.begin() as conn:
                for index_name in (
                    "ix_skills_emitted_at",
                    "ix_skills_process_entity_id",
                    "ix_skills_scope",
                    "ix_skills_skill_hash",
                    "ix_skills_skill_id",
                    "ix_skills_version",
                ):
                    conn.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
                conn.exec_driver_sql("DROP TABLE skills")
            Skill.__table__.create(bind=engine, checkfirst=True)
    else:
        Skill.__table__.create(bind=engine, checkfirst=True)
    if not inspector.has_table("skill_runs"):
        SkillRun.__table__.create(bind=engine, checkfirst=True)


def register_skill_with_session(
    session: Session,
    *,
    name: str,
    description: str,
    intent: str,
    prompt_template: str,
    llm_provider: str,
    llm_model: str,
    output_schema: dict[str, Any] | None = None,
    trigger_config: dict[str, Any] | None = None,
    trigger_type: str = "manual",
    created_by: str = "external_mcp_client",
) -> Skill:
    normalized_intent = _validate_choice(intent, VALID_INTENTS, "intent")
    normalized_trigger = _validate_choice(trigger_type, VALID_TRIGGER_TYPES, "trigger_type")
    if not name.strip():
        raise ValueError("name must not be empty")
    if not prompt_template.strip():
        raise ValueError("prompt_template must not be empty")
    row = Skill(
        name=name.strip(),
        description=description,
        intent=normalized_intent,
        trigger_type=normalized_trigger,
        trigger_config=trigger_config or {},
        prompt_template=prompt_template,
        output_schema=output_schema or {},
        llm_provider=llm_provider.strip().lower(),
        llm_model=llm_model.strip(),
        status="draft",
        created_by=created_by.strip() or "external_mcp_client",
        total_runs=0,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def activate_skill_with_session(session: Session, skill_id: str) -> Skill:
    row = session.get(Skill, skill_id)
    if row is None:
        raise SkillNotFound(skill_id)
    _validate_trigger_config(row.trigger_type, row.trigger_config or {})
    row.status = "active"
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_skills_with_session(
    session: Session,
    *,
    status: str | None = None,
    intent: str | None = None,
    trigger_type: str | None = None,
) -> list[Skill]:
    stmt = select(Skill)
    if status is not None:
        stmt = stmt.where(Skill.status == _validate_choice(status, VALID_STATUSES, "status"))
    if intent is not None:
        stmt = stmt.where(Skill.intent == _validate_choice(intent, VALID_INTENTS, "intent"))
    if trigger_type is not None:
        stmt = stmt.where(
            Skill.trigger_type == _validate_choice(trigger_type, VALID_TRIGGER_TYPES, "trigger_type")
        )
    stmt = stmt.order_by(desc(Skill.created_at), Skill.name)
    return session.execute(stmt).scalars().all()


def get_skill_with_session(session: Session, skill_id: str) -> Skill:
    row = session.get(Skill, skill_id)
    if row is None:
        raise SkillNotFound(skill_id)
    return row


def archive_skill_with_session(session: Session, skill_id: str) -> Skill:
    row = get_skill_with_session(session, skill_id)
    row.status = "archived"
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_skill_runs_with_session(
    session: Session,
    skill_id: str,
    limit: int = 50,
) -> list[SkillRun]:
    get_skill_with_session(session, skill_id)
    stmt = (
        select(SkillRun)
        .where(SkillRun.skill_id == skill_id)
        .order_by(desc(SkillRun.run_at), desc(SkillRun.id))
        .limit(limit)
    )
    return session.execute(stmt).scalars().all()


def register_skill(**kwargs: Any) -> dict[str, Any]:
    session = get_session()
    try:
        return skill_to_dict(register_skill_with_session(session, **kwargs))
    finally:
        session.close()


def activate_skill(skill_id: str) -> dict[str, Any]:
    session = get_session()
    try:
        return skill_to_dict(activate_skill_with_session(session, skill_id))
    finally:
        session.close()


def list_skills(status: str | None = None, intent: str | None = None) -> list[dict[str, Any]]:
    session = get_session()
    try:
        return [
            skill_to_dict(row)
            for row in list_skills_with_session(session, status=status, intent=intent)
        ]
    finally:
        session.close()


def get_skill(skill_id: str) -> dict[str, Any]:
    session = get_session()
    try:
        return skill_to_dict(get_skill_with_session(session, skill_id))
    finally:
        session.close()


def archive_skill(skill_id: str) -> dict[str, Any]:
    session = get_session()
    try:
        return skill_to_dict(archive_skill_with_session(session, skill_id))
    finally:
        session.close()
