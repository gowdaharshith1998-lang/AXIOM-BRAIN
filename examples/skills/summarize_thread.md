---
name: summarize_thread
description: Summarize a thread into decisions, risks, and next steps
intent: summarize
llm_provider: anthropic
llm_model: claude-3-haiku-20240307
scope_clusters: [customer_support, engineering_code]
trigger_type: manual
trigger_config: {}
output_schema:
  type: object
  required: [summary, next_steps]
  properties:
    summary:
      type: string
    next_steps:
      type: array
---
Summarize this thread for an agent that needs to act on it.

Thread: {thread_body}

Return concise JSON matching the output_schema.
