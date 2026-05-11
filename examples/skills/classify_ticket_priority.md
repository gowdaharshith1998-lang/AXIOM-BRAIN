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
