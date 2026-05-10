from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime
from string import Formatter
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.llm_keys import get_provider_key_plaintext_with_session
from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt
from axiom.schema.models import Skill, SkillRun
from axiom.skills.registry import SkillNotFound, get_skill_with_session, skill_run_to_dict
from axiom.storage.db import SessionLocal

RunEventCallback = Callable[[str, dict[str, Any]], None]

_HTTP_TIMEOUT = 30.0


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_prompt(template: str, payload: dict[str, Any]) -> str:
    flattened = _SafeFormatDict(payload)
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            flattened[key] = json.dumps(value, sort_keys=True)
    return Formatter().vformat(template, (), flattened)


def _content_from_response(provider: str, data: dict[str, Any]) -> str:
    if provider == "anthropic":
        chunks = data.get("content")
        if isinstance(chunks, list):
            text = "".join(str(item.get("text", "")) for item in chunks if isinstance(item, dict))
            if text:
                return text
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message["content"])
            if first.get("text") is not None:
                return str(first["text"])
    if data.get("text") is not None:
        return str(data["text"])
    return json.dumps(data, sort_keys=True)


def _call_provider(provider: str, model: str, api_key: str, prompt: str) -> str:
    if provider == "anthropic":
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_HTTP_TIMEOUT,
        )
    else:
        urls = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "groq": "https://api.groq.com/openai/v1/chat/completions",
            "mistral": "https://api.mistral.ai/v1/chat/completions",
        }
        response = httpx.post(
            urls[provider],
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_HTTP_TIMEOUT,
        )
    response.raise_for_status()
    return _content_from_response(provider, response.json())


def _coerce_output(content: str, schema: dict[str, Any]) -> dict[str, Any]:
    if not schema:
        return {"text": content}
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM output was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM output must be a JSON object")
    _validate_schema(parsed, schema)
    return parsed


def _validate_schema(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    required = schema.get("required", [])
    if isinstance(required, list):
        missing = [key for key in required if isinstance(key, str) and key not in payload]
        if missing:
            raise ValueError(f"LLM output missing required field(s): {', '.join(missing)}")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for key, spec in properties.items():
        if key not in payload or not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        py_type = type_map.get(expected)
        if py_type is not None and not isinstance(payload[key], py_type):
            raise ValueError(f"LLM output field {key!r} must be {expected}")


def _mark_skill_run_stats(session: Session, skill: Skill, run: SkillRun) -> None:
    skill.last_run_at = run.run_at
    skill.total_runs = int(skill.total_runs or 0) + 1
    skill.updated_at = datetime.utcnow()
    session.add(skill)


def _run_skill_with_session(
    session_factory: sessionmaker[Session],
    skill_id: str,
    input_payload: dict[str, Any],
    agent_name: str,
    *,
    event_callback: RunEventCallback | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    with session_factory() as session:
        skill = get_skill_with_session(session, skill_id)
        run = SkillRun(
            skill_id=skill.id,
            status="running",
            input_payload=input_payload,
            agent_name=agent_name,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        skill_snapshot = {
            "id": skill.id,
            "name": skill.name,
            "intent": skill.intent,
            "llm_provider": skill.llm_provider,
            "llm_model": skill.llm_model,
        }
        if event_callback is not None:
            event_callback(
                "skill_run_started",
                {"run": skill_run_to_dict(run), "skill": skill_snapshot},
            )

    try:
        with session_factory() as session:
            skill = get_skill_with_session(session, skill_id)
            api_key = get_provider_key_plaintext_with_session(session, skill.llm_provider)
            prompt = _render_prompt(skill.prompt_template, input_payload)
            content = _call_provider(skill.llm_provider, skill.llm_model, api_key, prompt)
            output = _coerce_output(content, skill.output_schema or {})
            run = session.get(SkillRun, run.id)
            if run is None:
                raise LookupError("skill run disappeared")
            run.status = "success"
            run.output_payload = output
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            _mark_skill_run_stats(session, skill, run)
            session.add(run)
            session.commit()
            session.refresh(run)

        receipt, _inserted = chain_insert_receipt(
            session_factory,
            ReceiptInsert(
                id=f"receipt_{run.id}",
                action_id=f"skill_run:{run.id}",
                agent_name=agent_name,
                intent=f"skill:{skill_snapshot['name']}",
                target_entity_id=None,
                cluster_id="skills",
                decision="allow",
                reason="skill run completed",
                policy_id="skill_runner",
                guidance=None,
                suggested_alternative=None,
                signing_scheme="demo",
                signature=uuid4().hex,
                demo_flag=False,
            ),
        )
        with session_factory() as session:
            persisted_run = session.get(SkillRun, run.id)
            if persisted_run is not None:
                persisted_run.receipt_id = receipt.id
                session.add(persisted_run)
                session.commit()
                session.refresh(persisted_run)
                result = skill_run_to_dict(persisted_run)
            else:
                result = skill_run_to_dict(run)
        if event_callback is not None:
            event_callback("skill_run_completed", {"run": result, "skill": skill_snapshot})
        return {"run": result, "skill": skill_snapshot}
    except Exception as exc:  # noqa: BLE001
        with session_factory() as session:
            failed = session.get(SkillRun, run.id)
            if failed is None:
                raise
            failed.status = "failed"
            failed.error_message = str(exc)
            failed.duration_ms = int((time.perf_counter() - started) * 1000)
            skill = session.get(Skill, skill_id)
            if skill is not None:
                _mark_skill_run_stats(session, skill, failed)
            session.add(failed)
            session.commit()
            session.refresh(failed)
            result = skill_run_to_dict(failed)
        if event_callback is not None:
            event_callback("skill_run_failed", {"run": result, "skill": skill_snapshot})
        return {"run": result, "skill": skill_snapshot}


def run_skill(
    skill_id: str,
    input_payload: dict[str, Any],
    agent_name: str,
    *,
    session_factory: sessionmaker[Session] | None = None,
    event_callback: RunEventCallback | None = None,
) -> dict[str, Any]:
    sf = session_factory or SessionLocal
    if sf is None:
        raise RuntimeError("database session is not initialized")
    try:
        return _run_skill_with_session(
            sf,
            skill_id,
            input_payload,
            agent_name,
            event_callback=event_callback,
        )
    except SkillNotFound:
        raise
