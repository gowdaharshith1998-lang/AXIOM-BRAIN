# AXIOM SKILL.md format

`SKILL.md` files are portable skill artifacts: YAML frontmatter plus a Markdown prompt body.

Required frontmatter keys:

- `name`
- `description`
- `intent`
- `llm_provider`
- `llm_model`
- `scope_clusters`
- `trigger_type`
- `output_schema`

Optional keys:

- `trigger_config`
- `requires_approval`
- `calibra_threshold`

Example:

```markdown
---
name: classify_ticket_priority
description: Classify support ticket priority from text
intent: classify
llm_provider: anthropic
llm_model: claude-3-haiku-20240307
scope_clusters: [customer_support, incidents_ops]
trigger_type: event
trigger_config:
  event_type: ticket.created
output_schema:
  type: object
  required: [priority, reason]
  properties:
    priority:
      type: string
      enum: [p0, p1, p2, p3]
    reason:
      type: string
---
Classify this support ticket's priority.

Ticket: {ticket_title}
Description: {ticket_body}

Return JSON matching the output_schema.
```

The body is stored as `prompt_template` and supports `{field}` placeholders from the skill run input payload.
