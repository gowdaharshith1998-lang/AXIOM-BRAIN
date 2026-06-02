from __future__ import annotations

import logging
import os
import random
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from axiom.policy import RealPolicyEvaluator, load_policies

logger = logging.getLogger("axiom.govern.policy_evaluator")
DENY_REASONS: tuple[str, ...] = (
    "no decision document references this skill",
    "agent lacks scope",
    "rate limit exceeded",
    "policy AEGIS-7 blocks write to billing without RFC",
)

RISKY_INTENTS: frozenset[str] = frozenset(
    {"delete", "modify_policy", "approve_exception", "force_push"}
)

CORRECT_IMPORTANCE_THRESHOLD: float = 0.45

CORRECT_GUIDANCE_TEMPLATES: tuple[str, ...] = (
    "High-importance entity targeted with destructive intent; consider read-only alternative",
    "Policy modification on critical entity requires elevated review",
    "Deletion blocked on high-importance node; suggest archival instead",
    "Exception approval on key entity diverted to governance review",
)


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    reason: str
    policy_id: str
    guidance: str = ""
    suggested_alternative: str | None = None


class DemoPolicyEvaluator:
    def __init__(
        self,
        deny_rate: float = 0.15,
        rng: random.Random | None = None,
        *,
        vault_unlocked: bool | None = None,
    ) -> None:
        self.deny_rate = deny_rate
        self.rng = rng or random.Random()
        self._reason_index = 0
        self._guidance_index = 0
        self._vault_unlocked_override = vault_unlocked

    @property
    def vault_unlocked(self) -> bool:
        if self._vault_unlocked_override is not None:
            return self._vault_unlocked_override
        return bool(os.environ.get("AXIOM_VAULT_KEY"))

    def evaluate(
        self,
        cluster_id: str,
        intent: str,
        *,
        entity_importance: float | None = None,
        suggested_alternative: str | None = None,
    ) -> PolicyDecision:
        if (
            entity_importance is not None
            and entity_importance >= CORRECT_IMPORTANCE_THRESHOLD
            and intent in RISKY_INTENTS
            and self.vault_unlocked
        ):
            guidance = CORRECT_GUIDANCE_TEMPLATES[
                self._guidance_index % len(CORRECT_GUIDANCE_TEMPLATES)
            ]
            self._guidance_index += 1
            return PolicyDecision(
                "correct",
                guidance,
                f"AEGIS-C{(self._guidance_index % 9) + 1}",
                guidance=guidance,
                suggested_alternative=suggested_alternative,
            )

        force_deny = cluster_id == "billing_payments" and intent == "write"
        if force_deny or self.rng.random() < self.deny_rate:
            reason = DENY_REASONS[self._reason_index % len(DENY_REASONS)]
            self._reason_index += 1
            return PolicyDecision("deny", reason, f"AEGIS-{(self._reason_index % 9) + 1}")
        return PolicyDecision("allow", "policy checks passed", "AEGIS-1")


def _is_production() -> bool:
    return os.environ.get("AXIOM_ENV", "").strip().lower() == "production"


def get_policy_evaluator(
    session_factory: Callable[[], Session] | None = None,
) -> RealPolicyEvaluator | DemoPolicyEvaluator:
    """Resolve the active policy evaluator, fail-closed in production (P1-1).

    In production a policy load failure or empty ruleset is fatal: the demo
    evaluator emits ``decision="allow"`` receipts (deny_rate=0), so silently
    falling back to it would govern nothing while looking like it does. Outside
    production we keep the demo fallback so local/dev/test runs stay usable.
    """
    try:
        rules = load_policies()
    except Exception as exc:  # noqa: BLE001
        if _is_production():
            raise SystemExit(
                f"FATAL: policy load failed in production; refusing to start fail-open: {exc}"
            ) from exc
        logger.warning(
            "could not load real policies; falling back to DemoPolicyEvaluator: %s",
            exc,
        )
        return DemoPolicyEvaluator(deny_rate=0)
    if not rules:
        if _is_production():
            raise SystemExit(
                "FATAL: no policies loaded in production; refusing to start "
                "fail-open (the demo evaluator allows everything)."
            )
        logger.warning("no real policies loaded; falling back to DemoPolicyEvaluator")
        return DemoPolicyEvaluator(deny_rate=0)
    return RealPolicyEvaluator(rules, session_factory)
