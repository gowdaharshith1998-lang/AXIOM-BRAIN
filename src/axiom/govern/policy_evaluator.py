from __future__ import annotations

import random
from dataclasses import dataclass

DENY_REASONS: tuple[str, ...] = (
    "no decision document references this skill",
    "agent lacks scope",
    "rate limit exceeded",
    "policy AEGIS-7 blocks write to billing without RFC",
)


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    reason: str
    policy_id: str


class DemoPolicyEvaluator:
    def __init__(self, deny_rate: float = 0.15, rng: random.Random | None = None) -> None:
        self.deny_rate = deny_rate
        self.rng = rng or random.Random()
        self._reason_index = 0

    def evaluate(self, cluster_id: str, intent: str) -> PolicyDecision:
        force_deny = cluster_id == "billing_payments" and intent == "write"
        if force_deny or self.rng.random() < self.deny_rate:
            reason = DENY_REASONS[self._reason_index % len(DENY_REASONS)]
            self._reason_index += 1
            return PolicyDecision("deny", reason, f"AEGIS-{(self._reason_index % 9) + 1}")
        return PolicyDecision("allow", "policy checks passed", "AEGIS-1")
