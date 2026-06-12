# Historical Documentation Guide

This guide separates current public documentation from archive material.

## Conflict Rule

When historical documents conflict with current docs, use this precedence:

1. [`../README.md`](../README.md)
2. [`PHASES.md`](PHASES.md)
3. [`ROADMAP.md`](ROADMAP.md)
4. Current runbooks such as [`PRODUCTION.md`](PRODUCTION.md)
5. Historical audits, dated reports, rebuild briefs, and older phase specs

## Archive Map

| Pattern | Status | Use |
| --- | --- | --- |
| `AUDIT_*.md` | Historical | Architecture and implementation audits from earlier snapshots. |
| `*AUDIT*.md` | Historical | Audit summaries, audit briefs, and line-by-line reviews. |
| `AXIOM_PHASE_5_12_SPEC.md` | Historical product spec | Useful for visual-brain context, not the active phase contract. |
| `CODEX_REBUILD_BRIEF.md` | Historical rebuild brief | Useful for reconstruction rationale. |
| `PRODUCTION_READINESS_*.md` | Dated readiness report | Point-in-time operational assessment. |
| `WHATS_WORKING_AND_YC_FIT_*.md` | Dated strategy report | Point-in-time product narrative and investor-readiness context. |
| Root `DESIGN.md` | Foundational design contract | Still test-covered, but README/PHASES/ROADMAP own public positioning. |

## Maintenance Rules

- Do not delete archive documents just because they contain old assumptions.
- Add a date to new audit or readiness reports.
- Put durable operating instructions in current runbooks, not dated reports.
- If an archive document becomes current again, link it from `docs/README.md`
  and explain the decision in `PHASES.md`.
