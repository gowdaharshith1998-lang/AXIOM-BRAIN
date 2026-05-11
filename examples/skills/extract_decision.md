---
name: extract_decision
description: Extract the decision, rationale, and owner from a discussion
intent: extract
llm_provider: anthropic
llm_model: claude-3-haiku-20240307
scope_clusters: [leadership_strategy, engineering_code]
trigger_type: manual
trigger_config: {}
output_schema:
  type: object
  required: [decision, rationale, owner]
  properties:
    decision:
      type: string
    rationale:
      type: string
    owner:
      type: string
---
Extract the durable decision from the source text.

Source: {source_text}

Return JSON matching the output_schema.
