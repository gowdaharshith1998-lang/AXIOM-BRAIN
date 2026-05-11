from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from axiom.policy.dsl import PolicyRule
from axiom.policy.predicates import reset_rate_history

PolicyMode = Literal["allow", "correct", "deny", "pause"]


@dataclass(frozen=True)
class ActionRequest:
    agent_name: str
    intent: str
    target_entity_id: str | None
    proposed_action: str
    idempotency_key: str | None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class PolicyDecision:
    mode: PolicyMode
    reason: str
    policy_id: str
    guidance: str | None = None
    suggested_alternative: dict[str, Any] | None = None
    approval_id: str | None = None
    fired_predicates: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _EvalContext:
    action: ActionRequest
    passport: Any
    entity: Any
    session: Session | None


class RealPolicyEvaluator:
    def __init__(
        self,
        rules: list[PolicyRule],
        session_factory: Callable[[], Session] | None,
    ) -> None:
        self.rules = list(rules)
        self._session_factory = session_factory
        reset_rate_history()

    def evaluate(
        self,
        action: ActionRequest,
        passport: Any,
        entity: Any | None,
    ) -> PolicyDecision:
        return self.evaluate_with_context(action, passport, entity)

    def evaluate_with_context(
        self,
        action: ActionRequest,
        passport: Any,
        entity: Any | None,
    ) -> PolicyDecision:
        if self._session_factory is None:
            return self._evaluate_in_session(action, passport, entity, None)
        with self._session_factory() as session:
            return self._evaluate_in_session(action, passport, entity, session)

    def _evaluate_in_session(
        self,
        action: ActionRequest,
        passport: Any,
        entity: Any | None,
        session: Session | None,
    ) -> PolicyDecision:
        context = _EvalContext(action=action, passport=passport, entity=entity, session=session)
        fired: list[str] = []
        for rule in self.rules:
            matched = bool(rule.when.evaluate(context))
            if matched:
                fired.append(rule.when.to_source())
                return PolicyDecision(
                    mode=rule.then.type,  # type: ignore[arg-type]
                    reason=_render_reason(rule.then.reason, action, passport, entity),
                    policy_id=rule.rule_id,
                    guidance=rule.then.guidance,
                    suggested_alternative=rule.then.suggested_alternative,
                    approval_id=None,
                    fired_predicates=fired,
                )
        return PolicyDecision(
            mode="allow",
            reason="policy checks passed",
            policy_id="default.allow",
            fired_predicates=fired,
        )


def _render_reason(template: str, action: ActionRequest, passport: Any, entity: Any | None) -> str:
    values = {
        "entity_id": getattr(entity, "id", None) or action.target_entity_id or "",
        "agent_name": action.agent_name,
        "intent": action.intent,
        "passport_id": getattr(passport, "passport_id", ""),
    }
    return template.format_map(_SafeFormat(values))


class _SafeFormat(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
