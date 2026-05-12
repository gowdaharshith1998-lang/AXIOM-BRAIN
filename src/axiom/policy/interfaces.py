from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

PolicyDecision = Literal["allow", "correct", "deny", "pause"]


@dataclass(frozen=True, slots=True)
class PolicyResult:
    decision: PolicyDecision
    policy_clause_id: str | None = None
    guidance: str | None = None
    reason: str | None = None
    retry_budget_remaining: int | None = None


class PolicyEngine(ABC):
    @abstractmethod
    def evaluate(self, *, agent_id: str, tool: str, params: dict[str, Any]) -> PolicyResult:
        raise NotImplementedError("PolicyEngine.evaluate is stubbed; lands in Phase 9")
