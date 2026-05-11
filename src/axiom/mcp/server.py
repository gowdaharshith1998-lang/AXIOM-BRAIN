from __future__ import annotations

import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, get_type_hints
from uuid import uuid4

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.api.search import _score_title
from axiom.govern.agent_registry import ensure_agent_registry_schema
from axiom.govern.demo_flag import is_demo_target
from axiom.govern.ledger import demo_receipt
from axiom.govern.passports import (
    PassportError,
    check_scope,
    ensure_passports_schema,
    ensure_system_passport,
    verify_passport,
)
from axiom.govern.policy_evaluator import CORRECT_IMPORTANCE_THRESHOLD, DemoPolicyEvaluator
from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt, ensure_receipts_schema, receipt_to_dict
from axiom.retrieval.search import SearchMode, hybrid_search
from axiom.schema.dto import EntityDTO
from axiom.schema.models import AgentPassport, Edge, Entity, Receipt
from axiom.skills.registry import (
    SkillNotFound,
    archive_skill_with_session,
    ensure_skills_schema,
    get_skill_with_session,
    list_skills_with_session,
    register_skill_with_session,
    skill_to_dict,
)
from axiom.skills.runner import run_skill
from axiom.storage import crud
from axiom.storage.db import init_engine
from axiom.studio.sources import ensure_sources_schema, real_sources_snapshot

Direction = Literal["outgoing", "incoming", "both"]
TITLE_KEYS = ("title", "name", "subject", "label")


@dataclass(frozen=True, slots=True)
class _EntityLite:
    id: str
    type: str
    source_id: str | None
    cluster_id: str | None
    composite_importance: float
    data: dict[str, Any]


class _GraphCache:
    def __init__(self) -> None:
        self.entities: dict[str, _EntityLite] = {}
        self.outgoing: dict[str, list[tuple[str, str, str]]] = {}
        self.incoming: dict[str, list[tuple[str, str, str]]] = {}


@dataclass(slots=True)
class _SyncState:
    entity_count: int = 0
    edge_count: int = 0
    last_entity_updated_at: datetime | None = None
    last_edge_created_at: datetime | None = None


def _title_from_data(entity_id: str, data: dict[str, Any]) -> str:
    for key in TITLE_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity_id


def _safe_fts_query(text: str) -> str:
    words = [w for w in text.strip().split() if w]
    if not words:
        return ""
    escaped = [f'"{w.replace("\"", "\"\"")}"*' for w in words[:6]]
    return " AND ".join(escaped)


class NavigationEventForwarder:
    def __init__(self, api_base_url: str = "http://127.0.0.1:8000") -> None:
        self._url = f"{api_base_url.rstrip('/')}/api/internal/agent-navigation"

    def emit_steps(
        self,
        steps: list[tuple[str, str, str | None]],
        *,
        agent_name: str = "external_mcp_client",
    ) -> None:
        if not steps:
            return
        sampled = steps[:50]
        payload = {
            "agent_name": agent_name,
            "steps": [
                {"from_id": from_id, "to_id": to_id, "edge_id": edge_id}
                for from_id, to_id, edge_id in sampled
            ],
        }
        try:
            with httpx.Client(timeout=0.5) as client:
                client.post(self._url, json=payload)
        except Exception:
            return

    def emit_action_events(self, *, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        try:
            with httpx.Client(timeout=0.5) as client:
                client.post(
                    self._url.replace("/agent-navigation", "/agent-action-events"),
                    json={"events": events},
                )
        except Exception:
            return


class AxiomMCPService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        event_forwarder: NavigationEventForwarder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._events = event_forwarder
        self._cache = _GraphCache()
        self._cache_lock = threading.Lock()
        self._cache_loaded_at = 0.0
        self._cache_ttl_sec = 10.0
        self._fts_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._fts_conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(entity_id UNINDEXED, searchable)"
        )
        self._sync_state = _SyncState()
        self._policy = DemoPolicyEvaluator(deny_rate=0)
        self._receipt_index = 0
        self._idempotency_ttl_sec = 3600.0
        self._idempotency: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
        self._action_history: dict[str, dict[str, Any]] = {}
        self._approval_queue: list[dict[str, Any]] = []
        bind = session_factory.kw.get("bind")
        if bind is not None:
            ensure_passports_schema(bind)
            ensure_receipts_schema(bind)
            ensure_agent_registry_schema(bind)
            ensure_skills_schema(bind)
            ensure_sources_schema(bind)
        ensure_system_passport(session_factory)
        self._hydrate_action_history_from_receipts()

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.utcnow().isoformat()

    @staticmethod
    def _target_entity_id_from_payload(payload: dict[str, Any]) -> str | None:
        for key in ("target_entity_id", "entity_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _demo_flag_for_target(self, target_entity_id: str | None) -> bool:
        with self._session_factory() as session:
            return is_demo_target(session, target_entity_id)

    def _cleanup_idempotency(self) -> None:
        now = time.monotonic()
        stale = [
            key
            for key, (created_at, _response) in self._idempotency.items()
            if now - created_at >= self._idempotency_ttl_sec
        ]
        for key in stale:
            del self._idempotency[key]

    @staticmethod
    def _action_output_from_receipt(receipt: Receipt) -> dict[str, Any]:
        return {
            "action_id": receipt.action_id,
            "decision": receipt.decision,
            "receipt_id": receipt.id,
            "signing_scheme": receipt.signing_scheme,
            "reason": receipt.reason,
            "policy_id": receipt.policy_id,
            "guidance": receipt.guidance,
            "suggested_alternative": receipt.suggested_alternative,
            "passport_id": receipt.passport_id,
            "demo": receipt.demo_flag,
        }

    def _resolve_passport(self, passport_token: str | None) -> AgentPassport:
        try:
            if passport_token:
                return verify_passport(self._session_factory, passport_token)
            return ensure_system_passport(self._session_factory)
        except PassportError as exc:
            raise ToolError(str(exc)) from exc

    def _require_passport_scope(
        self,
        *,
        passport_token: str | None,
        intent: str,
        cluster_id: str | None,
        skill_id: str | None = None,
    ) -> AgentPassport:
        passport = self._resolve_passport(passport_token)
        if not check_scope(passport, intent, cluster_id, skill_id):
            raise ToolError(
                f"passport scope denied for intent={intent!r}, cluster_id={cluster_id!r}, "
                f"skill_id={skill_id!r}"
            )
        return passport

    def _emit_action_events(self, events: list[dict[str, Any]]) -> None:
        if self._events is not None and events:
            self._events.emit_action_events(events=events)

    def _persist_policy_receipt(
        self,
        *,
        action_id: str,
        agent_name: str,
        intent: str,
        target_entity_id: str | None,
        cluster_id: str | None,
        evaluation: dict[str, Any],
        demo_flag: bool = True,
    ) -> tuple[Receipt, dict[str, Any]]:
        self._receipt_index += 1
        receipt_seed = demo_receipt(
            action_id=action_id,
            decision=str(evaluation["decision"]),
            agent_name=agent_name,
            index=self._receipt_index,
        )
        persisted, _inserted = chain_insert_receipt(
            self._session_factory,
            ReceiptInsert(
                id=str(receipt_seed["receipt_id"]),
                action_id=action_id,
                agent_name=agent_name,
                intent=intent,
                target_entity_id=target_entity_id,
                cluster_id=cluster_id,
                decision=str(evaluation["decision"]),
                reason=str(evaluation["reason"]),
                policy_id=str(evaluation["policy_id"]),
                guidance=evaluation["guidance"],
                suggested_alternative=evaluation["suggested_alternative"],
                signing_scheme=str(receipt_seed["signing_scheme"]),
                signature=str(receipt_seed.get("signature") or receipt_seed["merkle_root"]),
                passport_id=evaluation.get("passport_id"),
                demo_flag=demo_flag,
            ),
        )
        out = self._action_output_from_receipt(persisted)
        self._action_history[action_id] = out
        return persisted, out

    def _policy_preflight(
        self,
        *,
        agent_name: str,
        intent: str,
        target_entity_id: str | None,
        proposed_action: str,
        action_id: str | None = None,
        passport_token: str | None = None,
        scope_intent: str | None = None,
        skill_id: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        resolved_action_id = action_id or f"act_{uuid4().hex[:12]}"
        cluster_id, entity_importance, suggested_alternative = self._entity_context(target_entity_id)
        passport = self._require_passport_scope(
            passport_token=passport_token,
            intent=scope_intent or intent,
            cluster_id=cluster_id,
            skill_id=skill_id,
        )
        decision = self._policy.evaluate(
            cluster_id,
            intent,
            entity_importance=entity_importance,
            suggested_alternative=suggested_alternative,
        )
        return resolved_action_id, cluster_id, {
            "decision": decision.decision,
            "reason": decision.reason,
            "policy_id": decision.policy_id,
            "guidance": decision.guidance or None,
            "suggested_alternative": decision.suggested_alternative,
            "passport_id": passport.passport_id,
            "demo": self._demo_flag_for_target(target_entity_id),
        }

    def _emit_policy_result(
        self,
        *,
        event_type: str,
        action_id: str,
        agent_name: str,
        intent: str,
        target_entity_id: str | None,
        proposed_action: str,
        evaluation: dict[str, Any],
        receipt: Receipt,
    ) -> None:
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        payload = {
            "action_id": action_id,
            "agent_name": agent_name,
            "intent": intent,
            "target_entity_id": target_entity_id,
            "proposed_action": proposed_action,
            "decision": evaluation["decision"],
            "reason": evaluation["reason"],
            "policy_id": evaluation["policy_id"],
            "passport_id": evaluation.get("passport_id"),
            "guidance": evaluation["guidance"],
            "suggested_alternative": evaluation["suggested_alternative"],
            "timestamp": self._utcnow_iso(),
            "demo": receipt.demo_flag,
        }
        self._emit_action_events(
            [
                {
                    "type": event_type,
                    "source_id": None,
                    "persisted_id": action_id,
                    "payload": payload,
                    "timestamp": now_ms,
                },
                {
                    "type": "receipt_added",
                    "source_id": None,
                    "persisted_id": action_id,
                    "payload": receipt_to_dict(receipt),
                    "timestamp": now_ms,
                },
            ]
        )

    def _enforce_preflight(
        self,
        *,
        agent_name: str,
        intent: str,
        target_entity_id: str | None,
        proposed_action: str,
        action_id: str | None = None,
        passport_token: str | None = None,
        scope_intent: str | None = None,
        skill_id: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        resolved_action_id, cluster_id, evaluation = self._policy_preflight(
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            proposed_action=proposed_action,
            action_id=action_id,
            passport_token=passport_token,
            scope_intent=scope_intent,
            skill_id=skill_id,
        )
        decision = str(evaluation["decision"])
        if decision == "allow":
            return resolved_action_id, cluster_id, evaluation

        demo_flag = self._demo_flag_for_target(target_entity_id)
        receipt, out = self._persist_policy_receipt(
            action_id=resolved_action_id,
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            cluster_id=cluster_id,
            evaluation=evaluation,
            demo_flag=demo_flag,
        )
        event_type = "agent_action_blocked" if decision == "deny" else "agent_action_corrected"
        self._emit_policy_result(
            event_type=event_type,
            action_id=resolved_action_id,
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            proposed_action=proposed_action,
            evaluation=evaluation,
            receipt=receipt,
        )
        if decision == "deny":
            raise ToolError(f"{out['reason']} (policy_id={out['policy_id']})")
        return resolved_action_id, cluster_id, evaluation

    def _hydrate_action_history_from_receipts(self) -> None:
        with self._session_factory() as session:
            rows = session.execute(
                select(Receipt).order_by(desc(Receipt.created_at), desc(Receipt.id))
            ).scalars().all()
        self._action_history = {
            row.action_id: self._action_output_from_receipt(row)
            for row in rows
        }
        self._receipt_index = len(rows)

    def _entity_context(self, entity_id: str | None) -> tuple[str, float | None, str | None]:
        if entity_id is None:
            return "external_mcp", None, None
        with self._session_factory() as session:
            self._refresh_cache_if_needed(session)
        entity = self._cache.entities.get(entity_id)
        if entity is None:
            return "external_mcp", None, None
        suggested_alternative: str | None = None
        if entity.composite_importance >= CORRECT_IMPORTANCE_THRESHOLD:
            neighbors = self._cache.outgoing.get(entity_id, []) + self._cache.incoming.get(entity_id, [])
            ranked_neighbors = sorted(
                (
                    self._cache.entities[nid]
                    for nid, _edge_id, _rel in neighbors
                    if nid in self._cache.entities and nid != entity_id
                ),
                key=lambda item: (-item.composite_importance, item.id),
            )
            if ranked_neighbors:
                suggested_alternative = ranked_neighbors[0].id
        return entity.cluster_id or "external_mcp", entity.composite_importance, suggested_alternative

    def check_policy(
        self,
        *,
        agent_name: str,
        intent: str,
        target_entity_id: str | None,
        proposed_action: str,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        _action_id, _cluster_id, evaluation = self._policy_preflight(
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            proposed_action=proposed_action,
            passport_token=passport_token,
            scope_intent=intent,
        )
        return evaluation

    def record_action(
        self,
        *,
        agent_name: str,
        intent: str,
        target_entity_id: str | None,
        proposed_action: str,
        idempotency_key: str | None,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        self._cleanup_idempotency()
        if idempotency_key:
            existing = self._idempotency.get((agent_name, idempotency_key))
            if existing is not None:
                return existing[1]

        action_id, cluster_id, evaluation = self._policy_preflight(
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            proposed_action=proposed_action,
            passport_token=passport_token,
            scope_intent=intent,
        )
        demo_flag = self._demo_flag_for_target(target_entity_id)
        persisted, out = self._persist_policy_receipt(
            action_id=action_id,
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            cluster_id=cluster_id,
            evaluation=evaluation,
            demo_flag=demo_flag,
        )
        if idempotency_key:
            self._idempotency[(agent_name, idempotency_key)] = (time.monotonic(), out)

        if str(evaluation["decision"]) == "deny":
            self._emit_policy_result(
                event_type="agent_action_blocked",
                action_id=action_id,
                agent_name=agent_name,
                intent=intent,
                target_entity_id=target_entity_id,
                proposed_action=proposed_action,
                evaluation=evaluation,
                receipt=persisted,
            )
            raise ToolError(f"{out['reason']} (policy_id={out['policy_id']})")

        if self._events is not None:
            now_ms = int(datetime.utcnow().timestamp() * 1000)
            base_payload: dict[str, Any] = {
                "action_id": action_id,
                "agent_name": agent_name,
                "intent": intent,
                "target_entity_id": target_entity_id,
                "proposed_action": proposed_action,
                "timestamp": self._utcnow_iso(),
                "demo": demo_flag,
            }
            evaluated_payload = {
                **base_payload,
                "decision": out["decision"],
                "reason": out["reason"],
                "policy_id": out["policy_id"],
                "guidance": out["guidance"],
                "suggested_alternative": out["suggested_alternative"],
            }
            self._events.emit_action_events(
                events=[
                    {
                        "type": "agent_action",
                        "source_id": None,
                        "persisted_id": action_id,
                        "payload": base_payload,
                        "timestamp": now_ms,
                    },
                    {
                        "type": "agent_action_evaluated",
                        "source_id": None,
                        "persisted_id": action_id,
                        "payload": evaluated_payload,
                        "timestamp": now_ms,
                    },
                    {
                        "type": "receipt_added",
                        "source_id": None,
                        "persisted_id": action_id,
                        "payload": receipt_to_dict(persisted),
                        "timestamp": now_ms,
                    },
                ]
            )
        return out

    def request_human_approval(
        self,
        *,
        action_id: str,
        reason: str,
        agent_name: str,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        if action_id not in self._action_history:
            raise LookupError(f"unknown action id: {action_id}")
        approval_action_id, cluster_id, evaluation = self._enforce_preflight(
            agent_name=agent_name,
            intent="request_human_approval",
            target_entity_id=None,
            proposed_action=reason,
            passport_token=passport_token,
            scope_intent="write",
        )
        if str(evaluation["decision"]) == "correct":
            return {
                "status": "correct",
                "action_id": action_id,
                "reason": evaluation["reason"],
                "policy_id": evaluation["policy_id"],
                "guidance": evaluation["guidance"],
                "suggested_alternative": evaluation["suggested_alternative"],
                "demo": True,
            }
        item = {
            "queue_id": f"qa_{uuid4().hex[:12]}",
            "status": "pending",
            "created_at": self._utcnow_iso(),
            "action_id": action_id,
            "reason": reason,
            "agent_name": agent_name,
            "demo": False,
        }
        self._approval_queue.append(item)
        self._persist_policy_receipt(
            action_id=approval_action_id,
            agent_name=agent_name,
            intent="request_human_approval",
            target_entity_id=None,
            cluster_id=cluster_id,
            evaluation=evaluation,
            demo_flag=self._demo_flag_for_target(None),
        )
        return {
            "queue_id": item["queue_id"],
            "status": item["status"],
            "created_at": item["created_at"],
            "action_id": item["action_id"],
            "demo": item["demo"],
        }

    def list_skills(self, status: str | None = None, intent: str | None = None) -> dict[str, Any]:
        with self._session_factory() as session:
            rows = list_skills_with_session(session, status=status, intent=intent)
        return {"skills": [skill_to_dict(row) for row in rows], "count": len(rows)}

    def get_skill(self, skill_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            return {"skill": skill_to_dict(get_skill_with_session(session, skill_id))}

    def register_skill(
        self,
        *,
        name: str,
        description: str,
        intent: str,
        prompt_template: str,
        llm_provider: str,
        llm_model: str,
        output_schema: dict[str, Any] | None = None,
        trigger_config: dict[str, Any] | None = None,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        action_id, cluster_id, evaluation = self._enforce_preflight(
            agent_name="external_mcp_client",
            intent="register_skill",
            target_entity_id=None,
            proposed_action=name,
            passport_token=passport_token,
            scope_intent="write",
        )
        if str(evaluation["decision"]) == "correct":
            return {
                "decision": "correct",
                "reason": evaluation["reason"],
                "policy_id": evaluation["policy_id"],
                "guidance": evaluation["guidance"],
                "suggested_alternative": evaluation["suggested_alternative"],
                "demo": True,
            }
        with self._session_factory() as session:
            row = register_skill_with_session(
                session,
                name=name,
                description=description,
                intent=intent,
                prompt_template=prompt_template,
                llm_provider=llm_provider,
                llm_model=llm_model,
                output_schema=output_schema,
                trigger_config=trigger_config,
                created_by="external_mcp_client",
            )
            out = {"skill": skill_to_dict(row)}
        self._persist_policy_receipt(
            action_id=action_id,
            agent_name="external_mcp_client",
            intent="register_skill",
            target_entity_id=out["skill"]["id"],
            cluster_id=cluster_id,
            evaluation=evaluation,
            demo_flag=self._demo_flag_for_target(out["skill"]["id"]),
        )
        if self._events is not None:
            now_ms = int(datetime.utcnow().timestamp() * 1000)
            self._events.emit_action_events(
                events=[
                    {
                        "type": "skill_registered",
                        "source_id": None,
                        "persisted_id": out["skill"]["id"],
                        "payload": out,
                        "timestamp": now_ms,
                    }
                ]
            )
        return out

    def run_skill(
        self,
        *,
        skill_id: str,
        input_payload: dict[str, Any],
        idempotency_key: str | None = None,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        self._cleanup_idempotency()
        if idempotency_key:
            existing = self._idempotency.get(("skill_runner", idempotency_key))
            if existing is not None:
                return existing[1]

        with self._session_factory() as session:
            skill = get_skill_with_session(session, skill_id)
            skill_name = skill.name

        input_target_entity_id = self._target_entity_id_from_payload(input_payload)
        action_id, _cluster_id, evaluation = self._enforce_preflight(
            agent_name="external_mcp_client",
            intent=f"skill:{skill_name}",
            target_entity_id=None,
            proposed_action=f"axiom_run_skill:{skill_id}",
            action_id=f"skill_policy:{uuid4().hex[:12]}",
            passport_token=passport_token,
            scope_intent="invoke_skill",
            skill_id=skill_id,
        )
        if str(evaluation["decision"]) == "correct":
            out = {
                "action_id": action_id,
                "decision": "correct",
                "reason": evaluation["reason"],
                "policy_id": evaluation["policy_id"],
                "guidance": evaluation["guidance"],
                "suggested_alternative": evaluation["suggested_alternative"],
                "demo": True,
            }
            if idempotency_key:
                self._idempotency[("skill_runner", idempotency_key)] = (time.monotonic(), out)
            return out

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            if self._events is None:
                return
            self._events.emit_action_events(
                events=[
                    {
                        "type": event_type,
                        "source_id": None,
                        "persisted_id": skill_id,
                        "payload": payload,
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    }
                ]
            )

        out = run_skill(
            skill_id,
            input_payload,
            "external_mcp_client",
            session_factory=self._session_factory,
            event_callback=emit,
            receipt_policy_id=str(evaluation["policy_id"]),
            receipt_reason=str(evaluation["reason"]),
            receipt_passport_id=str(evaluation["passport_id"]),
            receipt_demo_flag=self._demo_flag_for_target(input_target_entity_id),
        )
        if idempotency_key:
            self._idempotency[("skill_runner", idempotency_key)] = (time.monotonic(), out)
        return out

    def archive_skill(self, skill_id: str, *, passport_token: str | None = None) -> dict[str, Any]:
        action_id, cluster_id, evaluation = self._enforce_preflight(
            agent_name="external_mcp_client",
            intent="archive_skill",
            target_entity_id=skill_id,
            proposed_action=f"axiom_archive_skill:{skill_id}",
            passport_token=passport_token,
            scope_intent="write",
        )
        if str(evaluation["decision"]) == "correct":
            return {
                "decision": "correct",
                "reason": evaluation["reason"],
                "policy_id": evaluation["policy_id"],
                "guidance": evaluation["guidance"],
                "suggested_alternative": evaluation["suggested_alternative"],
                "demo": True,
            }
        with self._session_factory() as session:
            row = archive_skill_with_session(session, skill_id)
            out = {"skill": skill_to_dict(row)}
        self._persist_policy_receipt(
            action_id=action_id,
            agent_name="external_mcp_client",
            intent="archive_skill",
            target_entity_id=skill_id,
            cluster_id=cluster_id,
            evaluation=evaluation,
            demo_flag=self._demo_flag_for_target(skill_id),
        )
        return out

    def _refresh_cache_if_needed(self, session: Session) -> None:
        now = time.monotonic()
        if now - self._cache_loaded_at < self._cache_ttl_sec:
            return
        with self._cache_lock:
            now = time.monotonic()
            if now - self._cache_loaded_at < self._cache_ttl_sec:
                return

            entity_count = int(session.execute(select(func.count(Entity.id))).scalar_one())
            edge_count = int(session.execute(select(func.count(Edge.id))).scalar_one())
            last_entity_updated_at = session.execute(select(func.max(Entity.updated_at))).scalar_one()
            last_edge_created_at = session.execute(select(func.max(Edge.created_at))).scalar_one()

            requires_full_rebuild = (
                self._sync_state.entity_count == 0
                or entity_count < self._sync_state.entity_count
                or edge_count < self._sync_state.edge_count
                or self._sync_state.last_entity_updated_at is None
                or self._sync_state.last_edge_created_at is None
            )

            if requires_full_rebuild:
                self._full_rebuild(session)
            else:
                self._incremental_sync(
                    session,
                    last_entity_updated_at=last_entity_updated_at,
                    last_edge_created_at=last_edge_created_at,
                )

            self._sync_state = _SyncState(
                entity_count=entity_count,
                edge_count=edge_count,
                last_entity_updated_at=last_entity_updated_at,
                last_edge_created_at=last_edge_created_at,
            )
            self._cache_loaded_at = now

    def _full_rebuild(self, session: Session) -> None:
        entities = session.execute(select(Entity)).scalars().all()
        edges = session.execute(select(Edge)).scalars().all()

        new_cache = _GraphCache()
        for row in entities:
            lite = _EntityLite(
                id=row.id,
                type=row.type,
                source_id=row.source_id,
                cluster_id=row.cluster_id,
                composite_importance=float(row.composite_importance or 0.0),
                data=row.data,
            )
            new_cache.entities[row.id] = lite
            new_cache.outgoing[row.id] = []
            new_cache.incoming[row.id] = []

        for edge in edges:
            if edge.source_id in new_cache.outgoing:
                new_cache.outgoing[edge.source_id].append((edge.target_id, edge.id, edge.relationship))
            if edge.target_id in new_cache.incoming:
                new_cache.incoming[edge.target_id].append((edge.source_id, edge.id, edge.relationship))

        cur = self._fts_conn.cursor()
        cur.execute("DELETE FROM entities_fts")
        rows = []
        for ent in new_cache.entities.values():
            rows.append((ent.id, self._searchable_text(ent)))
        cur.executemany("INSERT INTO entities_fts(entity_id, searchable) VALUES (?, ?)", rows)
        self._fts_conn.commit()
        self._cache = new_cache

    def _incremental_sync(
        self,
        session: Session,
        *,
        last_entity_updated_at: datetime | None,
        last_edge_created_at: datetime | None,
    ) -> None:
        if self._sync_state.last_entity_updated_at is not None and last_entity_updated_at is not None:
            changed_entities = session.execute(
                select(Entity).where(Entity.updated_at > self._sync_state.last_entity_updated_at)
            ).scalars().all()
            if changed_entities:
                cur = self._fts_conn.cursor()
                for row in changed_entities:
                    lite = _EntityLite(
                        id=row.id,
                        type=row.type,
                        source_id=row.source_id,
                        cluster_id=row.cluster_id,
                        composite_importance=float(row.composite_importance or 0.0),
                        data=row.data,
                    )
                    self._cache.entities[row.id] = lite
                    self._cache.outgoing.setdefault(row.id, [])
                    self._cache.incoming.setdefault(row.id, [])
                    cur.execute("DELETE FROM entities_fts WHERE entity_id = ?", (row.id,))
                    cur.execute(
                        "INSERT INTO entities_fts(entity_id, searchable) VALUES (?, ?)",
                        (row.id, self._searchable_text(lite)),
                    )
                self._fts_conn.commit()

        if self._sync_state.last_edge_created_at is not None and last_edge_created_at is not None:
            new_edges = session.execute(
                select(Edge).where(Edge.created_at > self._sync_state.last_edge_created_at)
            ).scalars().all()
            for edge in new_edges:
                self._cache.outgoing.setdefault(edge.source_id, []).append(
                    (edge.target_id, edge.id, edge.relationship)
                )
                self._cache.incoming.setdefault(edge.target_id, []).append(
                    (edge.source_id, edge.id, edge.relationship)
                )

    @staticmethod
    def _searchable_text(ent: _EntityLite) -> str:
        title = _title_from_data(ent.id, ent.data)
        name = str(ent.data.get("name", ""))
        subject = str(ent.data.get("subject", ""))
        label = str(ent.data.get("label", ""))
        return f"{title} {name} {subject} {label}".strip()

    def query_brain(
        self,
        query: str,
        max_results: int,
        entity_types: list[str] | None = None,
        cluster_id: str | None = None,
        mode: SearchMode = "hybrid",
    ) -> dict[str, Any]:
        q = query.strip()
        if not q:
            return {"results": [], "count": 0}

        safe_limit = min(max(max_results, 1), 50)
        with self._session_factory() as session:
            self._refresh_cache_if_needed(session)
            out = hybrid_search(
                session,
                q,
                mode=mode,
                top_k=safe_limit,
                entity_types=entity_types,
                cluster_id=cluster_id,
            )

        for row in out["results"]:
            methods = row.get("methods", [])
            row["matched_on"] = row.get("matched_on") or (
                "query_match"
                if "lexical" in methods or "semantic" in methods
                else "graph_match"
            )
        return out

        fts_query = _safe_fts_query(q)
        seed_ids: list[str] = []
        if fts_query:
            try:
                cur = self._fts_conn.cursor()
                cur.execute(
                    "SELECT entity_id FROM entities_fts WHERE entities_fts MATCH ? LIMIT ?",
                    (fts_query, 600),
                )
                seed_ids = [str(row[0]) for row in cur.fetchall()]
            except Exception:
                seed_ids = []

        if not seed_ids:
            seed_ids = list(self._cache.entities.keys())[:600]

        seeds: list[tuple[_EntityLite, float]] = []
        for entity_id in seed_ids:
            entity = self._cache.entities.get(entity_id)
            if entity is None:
                continue
            if entity_types and entity.type not in entity_types:
                continue
            if cluster_id is not None and entity.cluster_id != cluster_id:
                continue
            score = _score_title(q, _title_from_data(entity.id, entity.data))
            if score > 0:
                seeds.append((entity, score))

        seeds.sort(key=lambda item: (-item[1], -item[0].composite_importance, item[0].id))
        seeds = seeds[:safe_limit]

        candidate_map: dict[str, dict[str, Any]] = {}
        nav_steps: list[tuple[str, str, str | None]] = []

        for entity, match_score in seeds:
            candidate_map[entity.id] = self._entity_result(entity, "query_match", match_score)

            neighbors = self._cache.outgoing.get(entity.id, []) + self._cache.incoming.get(entity.id, [])
            for neighbor_id, edge_id, _rel in neighbors:
                neighbor = self._cache.entities.get(neighbor_id)
                if neighbor is None:
                    continue
                if entity_types and neighbor.type not in entity_types:
                    continue
                if cluster_id is not None and neighbor.cluster_id != cluster_id:
                    continue
                nav_steps.append((entity.id, neighbor.id, edge_id))
                if neighbor.id in candidate_map:
                    continue
                neighbor_score = max(0.0, match_score - 0.2)
                candidate_map[neighbor.id] = {
                    "id": neighbor.id,
                    "type": neighbor.type,
                    "data": neighbor.data,
                    "source_id": neighbor.source_id,
                    "cluster_id": neighbor.cluster_id,
                    "composite_importance": neighbor.composite_importance,
                    "title": _title_from_data(neighbor.id, neighbor.data),
                    "score": round(neighbor.composite_importance, 6),
                    "match_score": round(float(neighbor_score), 6),
                    "matched_on": f"neighbor_of:{entity.id}",
                }

        if self._events is not None:
            self._events.emit_steps(nav_steps)

        ranked = sorted(
            candidate_map.values(),
            key=lambda item: (
                -float(item.get("score", 0.0)),
                -float(item.get("match_score", 0.0)),
                str(item["id"]),
            ),
        )
        return {"results": ranked[:safe_limit], "count": len(ranked[:safe_limit])}

    def get_entity(
        self,
        entity_id: str,
        include_neighbors: bool = False,
        hops: int = 1,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            entity = session.get(Entity, entity_id)
            if entity is None:
                raise LookupError(f"unknown entity id: {entity_id}")

            result: dict[str, Any] = {
                "entity": {
                    **EntityDTO.model_validate(entity).model_dump(mode="json"),
                    "title": _title_from_data(entity.id, entity.data),
                }
            }
            if include_neighbors:
                safe_hops = min(max(hops, 1), 2)
                neighbors = crud.list_neighbors(session, entity_id, depth=safe_hops, direction="both")
                result["neighbors"] = [
                    {**neighbor.model_dump(mode="json"), "title": _title_from_data(neighbor.id, neighbor.data)}
                    for neighbor in neighbors
                ]
                if self._events is not None:
                    self._events.emit_steps([(entity_id, n.id, None) for n in neighbors])
            return result

    def traverse(
        self,
        from_id: str,
        edge_types: list[str] | None = None,
        max_depth: int = 2,
        direction: Direction = "both",
    ) -> dict[str, Any]:
        safe_depth = min(max(max_depth, 1), 6)
        cap = 200

        with self._session_factory() as session:
            self._refresh_cache_if_needed(session)

        if from_id not in self._cache.entities:
            raise LookupError(f"unknown entity id: {from_id}")

        visited: set[str] = {from_id}
        q: deque[tuple[str, int]] = deque([(from_id, 0)])
        nodes: list[dict[str, Any]] = []
        edges_out: list[dict[str, Any]] = []
        nav_steps: list[tuple[str, str, str | None]] = []

        while q and len(visited) < cap:
            current_id, depth = q.popleft()
            nodes.append({"id": current_id, "depth": depth})
            if depth >= safe_depth:
                continue

            rels: list[tuple[str, str, str]] = []
            if direction in ("outgoing", "both"):
                rels.extend(self._cache.outgoing.get(current_id, []))
            if direction in ("incoming", "both"):
                rels.extend(self._cache.incoming.get(current_id, []))

            for next_id, edge_id, relationship in rels:
                if edge_types and relationship not in edge_types:
                    continue
                edges_out.append(
                    {
                        "edge_id": edge_id,
                        "from_id": current_id,
                        "to_id": next_id,
                        "relationship": relationship,
                        "depth": depth + 1,
                    }
                )
                nav_steps.append((current_id, next_id, edge_id))
                if next_id in visited:
                    continue
                visited.add(next_id)
                if len(visited) >= cap:
                    break
                q.append((next_id, depth + 1))

        if self._events is not None:
            self._events.emit_steps(nav_steps)

        return {
            "root_id": from_id,
            "direction": direction,
            "max_depth": safe_depth,
            "node_cap": cap,
            "nodes": nodes,
            "edges": edges_out,
            "truncated": len(visited) >= cap,
        }

    def list_sources(self) -> dict[str, Any]:
        with self._session_factory() as session:
            rows = real_sources_snapshot(session)
        return {"sources": rows, "count": len(rows)}

    @staticmethod
    def _entity_result(entity: _EntityLite, matched_on: str, match_score: float) -> dict[str, Any]:
        return {
            "id": entity.id,
            "type": entity.type,
            "title": _title_from_data(entity.id, entity.data),
            "source_id": entity.source_id,
            "cluster_id": entity.cluster_id,
            "score": round(entity.composite_importance, 6),
            "match_score": round(float(match_score), 6),
            "matched_on": matched_on,
        }


def build_mcp_server(
    *,
    db_url: str = "sqlite:///./axiom.db",
    api_base_url: str = "http://127.0.0.1:8000",
) -> FastMCP:
    engine = init_engine(db_url)
    session_local = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    service = AxiomMCPService(
        session_factory=session_local,
        event_forwarder=NavigationEventForwarder(api_base_url=api_base_url),
    )

    mcp = FastMCP(name="AXIOM MCP")

    def tool(
        *,
        name: str,
        description: str,
        annotations: Any | None = None,
    ) -> Any:
        def decorator(fn: Any) -> Any:
            # MCP 1.9.4 expects runtime annotation classes when checking for Context.
            fn.__annotations__ = get_type_hints(fn)
            mcp.add_tool(fn, name=name, description=description, annotations=annotations)
            return fn

        return decorator

    @tool(name="axiom_query_brain", description="Smart search over entities with 1-hop expansion")
    def axiom_query_brain(
        query: str,
        max_results: int = 8,
        entity_types: list[str] | None = None,
        cluster_id: str | None = None,
        mode: SearchMode = "hybrid",
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        service._require_passport_scope(
            passport_token=passport_token,
            intent="read",
            cluster_id=cluster_id or "external_mcp",
        )
        return service.query_brain(query, max_results, entity_types, cluster_id, mode)

    @tool(name="axiom_get_entity", description="Fetch one entity and optional neighbors")
    def axiom_get_entity(
        entity_id: str,
        include_neighbors: bool = False,
        hops: int = 1,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            cluster_id, _importance, _alternative = service._entity_context(entity_id)
            service._require_passport_scope(
                passport_token=passport_token,
                intent="read",
                cluster_id=cluster_id,
            )
            return service.get_entity(entity_id, include_neighbors, hops)
        except LookupError as exc:
            raise ToolError(str(exc)) from exc

    @tool(name="axiom_traverse", description="BFS graph traversal with cycle detection")
    def axiom_traverse(
        from_id: str,
        edge_types: list[str] | None = None,
        max_depth: int = 2,
        direction: Direction = "both",
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            cluster_id, _importance, _alternative = service._entity_context(from_id)
            service._require_passport_scope(
                passport_token=passport_token,
                intent="read",
                cluster_id=cluster_id,
            )
            return service.traverse(from_id, edge_types, max_depth, direction)
        except LookupError as exc:
            raise ToolError(str(exc)) from exc

    @tool(name="axiom_list_sources", description="List connected sources")
    def axiom_list_sources(passport_token: str | None = None) -> dict[str, Any]:
        service._require_passport_scope(
            passport_token=passport_token,
            intent="read",
            cluster_id="external_mcp",
        )
        return service.list_sources()

    @tool(name="axiom_record_action", description="Record an external agent action with demo policy evaluation")
    def axiom_record_action(
        agent_name: str,
        intent: str,
        target_entity_id: str | None = None,
        proposed_action: str = "",
        idempotency_key: str | None = None,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        return service.record_action(
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            proposed_action=proposed_action,
            idempotency_key=idempotency_key,
            passport_token=passport_token,
        )

    @tool(name="axiom_check_policy", description="Pre-flight policy check for an action proposal")
    def axiom_check_policy(
        agent_name: str,
        intent: str,
        target_entity_id: str | None = None,
        proposed_action: str = "",
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        return service.check_policy(
            agent_name=agent_name,
            intent=intent,
            target_entity_id=target_entity_id,
            proposed_action=proposed_action,
            passport_token=passport_token,
        )

    @tool(
        name="axiom_request_human_approval",
        description="Escalate an action for human approval via in-memory queue",
    )
    def axiom_request_human_approval(
        action_id: str,
        reason: str,
        agent_name: str,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            return service.request_human_approval(
                action_id=action_id,
                reason=reason,
                agent_name=agent_name,
                passport_token=passport_token,
            )
        except LookupError as exc:
            raise ToolError(str(exc)) from exc

    @tool(name="axiom_list_skills", description="List registered runnable skills")
    def axiom_list_skills(
        status: str | None = None,
        intent: str | None = None,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            service._require_passport_scope(
                passport_token=passport_token,
                intent="read",
                cluster_id="skills",
            )
            return service.list_skills(status=status, intent=intent)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @tool(name="axiom_get_skill", description="Fetch a registered skill by id")
    def axiom_get_skill(skill_id: str, passport_token: str | None = None) -> dict[str, Any]:
        try:
            service._require_passport_scope(
                passport_token=passport_token,
                intent="read",
                cluster_id="skills",
                skill_id=skill_id,
            )
            return service.get_skill(skill_id)
        except SkillNotFound as exc:
            raise ToolError(str(exc)) from exc

    @tool(name="axiom_run_skill", description="Run a registered skill with an input payload")
    def axiom_run_skill(
        skill_id: str,
        input_payload: dict[str, Any],
        idempotency_key: str | None = None,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            return service.run_skill(
                skill_id=skill_id,
                input_payload=input_payload,
                idempotency_key=idempotency_key,
                passport_token=passport_token,
            )
        except SkillNotFound as exc:
            raise ToolError(str(exc)) from exc

    @tool(name="axiom_register_skill", description="Register a draft skill")
    def axiom_register_skill(
        name: str,
        description: str,
        intent: str,
        prompt_template: str,
        llm_provider: str,
        llm_model: str,
        output_schema: dict[str, Any] | None = None,
        trigger_config: dict[str, Any] | None = None,
        passport_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            return service.register_skill(
                name=name,
                description=description,
                intent=intent,
                prompt_template=prompt_template,
                llm_provider=llm_provider,
                llm_model=llm_model,
                output_schema=output_schema,
                trigger_config=trigger_config,
                passport_token=passport_token,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @tool(name="axiom_archive_skill", description="Archive a skill")
    def axiom_archive_skill(skill_id: str, passport_token: str | None = None) -> dict[str, Any]:
        try:
            return service.archive_skill(skill_id, passport_token=passport_token)
        except SkillNotFound as exc:
            raise ToolError(str(exc)) from exc

    return mcp


def serve_stdio(*, db_url: str = "sqlite:///./axiom.db", api_base_url: str = "http://127.0.0.1:8000") -> None:
    mcp = build_mcp_server(db_url=db_url, api_base_url=api_base_url)
    mcp.run(transport="stdio")
