from __future__ import annotations

from axiom.govern.watchdog_rules import DEFAULT_RULES
from axiom.policy.dsl import PolicyAction, PolicyRule, parse_predicate


def watchdog_rules_as_policies() -> list[PolicyRule]:
    rules: list[PolicyRule] = []
    for rule in DEFAULT_RULES:
        rule_id = _rule_id(rule.__name__)
        rules.append(
            PolicyRule(
                rule_id=f"watchdog.{rule_id}.{rule.__name__}",
                description=f"Pause agent actions while watchdog rule {rule_id} is open.",
                severity="critical" if rule_id == "R2" else "warning",
                when=parse_predicate(
                    f'watchdog.has_open_alert_on(entity, rule_id="{rule_id}") == true'
                ),
                then=PolicyAction(
                    type="pause",
                    reason=f"Watchdog rule {rule_id} fired on target entity",
                    approval_required_role="ops",
                    approval_timeout_seconds=1800,
                ),
                metadata={
                    "source": "watchdog",
                    "watchdog_rule_id": rule_id,
                    "category": "watchdog",
                    "customer_facing": True,
                    "tags": ["watchdog", rule_id],
                },
            )
        )
    return rules


def _rule_id(function_name: str) -> str:
    names = {
        "billing_change_without_decision": "R1",
        "ticket_severity_mismatch_runbook": "R2",
        "policy_doc_orphaned": "R3",
        "confidence_drift_high": "R4",
        "cluster_outlier": "R5",
        "stale_decision_referenced": "R6",
        "process_without_compiled_skill": "R7",
    }
    return names[function_name]
