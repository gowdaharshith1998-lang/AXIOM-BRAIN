# AXIOM Brain Documentation

This directory mixes current operator documentation with historical audit and
design material. Use this index to find the right source of truth quickly.

## Current Orientation

| Document | Purpose |
| --- | --- |
| [`../README.md`](../README.md) | Repository overview, local setup, verification commands, and production boundary. |
| [`PHASES.md`](PHASES.md) | Current phase guide and status language for AXIOM Brain. |
| [`ROADMAP.md`](ROADMAP.md) | Product and engineering priorities. |
| [`PRODUCTION.md`](PRODUCTION.md) | Single-tenant deployment, health checks, backups, and operational controls. |
| [`CONNECTORS.md`](CONNECTORS.md) | Connector setup and integration notes. |
| [`POLICIES.md`](POLICIES.md) | Policy model and starter-pack guidance. |
| [`SKILLS.md`](SKILLS.md) | Skill and SkillFile concepts. |

## Historical Context

Audit reports, rebuild briefs, dated readiness reports, and older phase specs are
preserved for traceability. They can explain why certain choices exist, but they
are not the current product contract when they conflict with the README,
`PHASES.md`, or `ROADMAP.md`.

See [`HISTORICAL.md`](HISTORICAL.md) for the archive map and conflict rule.

## Maintenance Rules

- Keep setup, test, build, and deploy commands aligned with CI.
- Keep AXIOM Brain product language separate from AXIOM Control context.
- Update this index when adding a new durable document.
- Label time-bound audits, pitches, and rebuild notes as historical.
