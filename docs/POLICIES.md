# AXIOM Policy Rules

AXIOM policies are ordered YAML rules. The evaluator walks rules in file order and returns the first matching rule. If nothing matches, the default decision is `allow`.

## YAML Format

```yaml
rules:
  - rule_id: starter.passport.revoked
    description: Deny any action from a revoked passport.
    severity: critical
    when: passport.status == "revoked"
    then:
      type: deny
      reason: "Passport {passport_id} is revoked, cannot {intent}"
    metadata:
      category: passport_state
      customer_facing: true
      tags: [passport, revoked]
```

Required fields are `rule_id`, `description`, `severity`, `when`, and `then`. `severity` must be `info`, `warning`, or `critical`. `then.type` must be `allow`, `correct`, `deny`, or `pause`.

## Predicates

The policy DSL supports comparisons, lists, boolean composition, and parentheses:

```text
entity.type == "ticket"
entity.cluster_id in ["billing_payments", "incidents_ops"]
passport.scope_clusters contains entity.cluster_id
action.intent == "write" and confidence < 0.4
not passport.scope_intents contains action.intent
```

Available built-in predicates:

- `contains_pii()` checks strings, lists, and objects for emails, SSNs, credit cards, and phone numbers.
- `watchdog.has_open_alert_on(entity, rule_id="R5")` checks active watchdog alerts.
- `watchdog.alert_count(entity, severity="critical")` counts active watchdog alerts.
- `rate.same_action_within(seconds=60)` detects repeated actions for the same agent, intent, and target.
- `time.off_hours_utc(start_hour=20, end_hour=7)` checks the action timestamp against UTC hours.
- `now()` and `days(30)` can be used in timestamp comparisons.

## Actions

`allow` permits execution. `correct` returns guidance and an optional `suggested_alternative`. `deny` blocks execution. `pause` blocks execution until an approval flow resolves the action.

Reason templates support `{entity_id}`, `{agent_name}`, `{intent}`, and `{passport_id}`.

## Examples

Correct PII before retrying:

```yaml
when: data.payload contains_pii() == true
then:
  type: correct
  reason: "Payload for {intent} on {entity_id} appears to contain PII"
  guidance: "Redact personal data before retrying."
```

Pause high-risk exports:

```yaml
when: action.intent == "export" and action.payload.destination == "external"
then:
  type: pause
  reason: "External export requested for {entity_id}"
  approval_required_role: data_owner
  approval_timeout_seconds: 3600
```

Deny revoked passports:

```yaml
when: passport.status == "revoked"
then:
  type: deny
  reason: "Passport {passport_id} is revoked, cannot {intent}"
```

## Custom Rules

Place custom YAML files in `AXIOM_POLICY_DIR` or under `policies/`. Files are loaded lexically. Keep rule IDs namespaced, for example `acme.data.export_external`, and put the highest-risk deny or pause rules before broad correction rules.

## Testing Rules

Run focused policy tests after editing rules:

```bash
PYTHONPATH=src pytest tests/test_policy_dsl.py tests/test_policy_starter_pack.py -q
```

For endpoint and MCP wiring checks:

```bash
PYTHONPATH=src pytest tests/test_policy_wiring.py tests/test_mcp_write_tools.py -q
```
