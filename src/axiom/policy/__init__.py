
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .dsl import (
    PolicyAction,
    PolicyParseError,
    PolicyRule,
    load_policies_from_dir,
    parse_policy_yaml,
)
from .evaluator import ActionRequest, PolicyDecision, RealPolicyEvaluator
from .interfaces import PolicyDecision as LegacyPolicyDecision
from .interfaces import PolicyEngine, PolicyResult


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def load_policies() -> list[PolicyRule]:
    from .watchdog_integration import watchdog_rules_as_policies

    policy_dir = Path(os.environ.get("AXIOM_POLICY_DIR", _repo_root() / "policies"))
    return [*watchdog_rules_as_policies(), *load_policies_from_dir(policy_dir)]


def reload_policies() -> list[PolicyRule]:
    load_policies.cache_clear()
    return load_policies()


__all__ = [
    "ActionRequest",
    "LegacyPolicyDecision",
    "PolicyAction",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyParseError",
    "PolicyResult",
    "PolicyRule",
    "RealPolicyEvaluator",
    "load_policies",
    "load_policies_from_dir",
    "parse_policy_yaml",
    "reload_policies",
]
