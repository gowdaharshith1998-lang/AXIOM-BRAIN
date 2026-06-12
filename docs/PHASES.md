# AXIOM Brain Project Phases

This document is the current phase guide for AXIOM Brain. Older audit, rebuild, and pitch documents in `docs/` are preserved as historical context unless they are explicitly linked from this file as current.

For the full documentation map, see the [`docs/` index](README.md). For archive precedence and conflict rules, see the [historical docs guide](HISTORICAL.md).

## Product Boundary

| Name | Meaning |
| --- | --- |
| AXIOM Brain | The product in this repository: a live company knowledge graph and operator console. |
| AXIOM-BRAIN | The GitHub repository slug and container/release identifier. |
| `axiom` | The Python package, CLI command, environment-variable prefix, and MCP tool namespace. |
| AXIOM Control | Separate company/product context. It is not an alias for AXIOM Brain. |
| company brain | Category language for the kind of system AXIOM Brain implements. |

## Current Baseline

Status: active single-tenant product baseline

- Version baseline: `0.2.0`.
- Backend: Python 3.13, FastAPI, SQLite, SQLAlchemy, Alembic, MCP stdio server.
- Frontend: React, Vite, TypeScript, Three.js, Zustand.
- Operational posture: local development and controlled single-tenant deployment.
- Production boundary: HTTPS, strong API token, configured vault key, demo fallbacks disabled, and scheduled SQLite backups.
- Not yet included: managed multi-tenant SaaS, per-user identity, tenant isolation, admin RBAC, managed database infrastructure, or full hosted observability.

## Phase 1: Foundation

Status: complete

- Established the Python package and CLI namespace.
- Added the FastAPI backend, React/Vite frontend, SQLite storage, and Alembic migrations.
- Added the universal entity/edge model and synthetic source fixtures.
- Created the first Studio API and 3D graph surface.
- Added initial CI structure and backend/frontend test suites.

## Phase 2: Production Hardening

Status: complete as of `0.2.0`

- Added Docker and Compose production paths.
- Added boot-time Alembic migration support.
- Hardened production auth defaults.
- Added SQLite WAL, busy-timeout, and foreign-key setup.
- Added encrypted vault handling for connector and provider secrets.
- Added CI gates for lockfile drift, lint, types, tests, migrations, and frontend build.
- Added backup, restore, health-check, readiness, and metrics runbooks.

## Phase 3: Public Repository Surface

Status: in progress

- Keep README setup commands aligned with the installed `axiom` CLI and CI workflow.
- Keep `docs/README.md` as the documentation landing page.
- Keep `docs/HISTORICAL.md` as the archive map for dated audits and rebuild briefs.
- Separate AXIOM Brain product naming from AXIOM Control company/product context.
- Keep `AXIOM-BRAIN` as a repository identifier, not a user-facing product name.
- Keep historical docs clearly separated from current public orientation docs.
- Maintain contributor, security, code-of-conduct, issue-template, and pull-request-template files.
- Maintain CodeQL workflow coverage for Python and TypeScript/JavaScript.

## Phase 4: AXIOM Brain Experience

Status: active product track

- Improve the visual graph experience: layout, inspector, live stats, search, focus, and camera interactions.
- Keep the frontend wired to real REST bootstrap and WebSocket updates.
- Preserve auth and WebSocket token behavior.
- Refactor frontend shell and renderer modules in small, tested slices.
- Verify major visual changes with focused frontend tests and browser checks when UI behavior changes.

## Phase 5: Governance, Skills, And Connectors

Status: ongoing

- Expand connector reliability and source sync.
- Continue governance, passport, policy, receipt, approval, and watchdog surfaces.
- Harden SkillFile and MCP workflows around real storage and signed receipts.
- Preserve existing route paths, MCP tool names, vault plaintext discipline, and signed-receipt behavior unless a targeted migration plan exists.
- Keep reserved confidence fields as schema compatibility details, not as public claims of an integrated external calibration system.

## Phase 6: SaaS Readiness

Status: planned

- Add per-user identity and tenant isolation.
- Move from single-tenant operational assumptions to managed multi-tenant infrastructure.
- Add admin RBAC, audit identity, managed database strategy, and deeper observability.
- Define hosted-product boundaries separately from this open repository.

## Historical Phase Documents

These files are useful for archaeology, audits, and context, but are not the current public phase guide:

- `DESIGN.md`
- `docs/ROADMAP.md` before the 2026-06-09 rewrite
- `docs/AXIOM_PHASE_5_12_SPEC.md`
- `docs/CODEX_REBUILD_BRIEF.md`
- `docs/AUDIT_*`
- `docs/*AUDIT*`
- dated production-readiness and YC-fit reports

When historical documents conflict with this file or the README, use this file and the README for current public positioning.

## Decision Log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-06-09 | Present the product in this repo as AXIOM Brain. | The user clarified AXIOM Control and AXIOM Brain are different. |
| 2026-06-09 | Keep `AXIOM-BRAIN` as the repository identifier only. | Avoids confusing repo slug with product copy. |
| 2026-06-09 | Keep `axiom` as the CLI/package/MCP namespace. | It is already wired through code, tests, docs, and environment variables. |
| 2026-06-09 | Treat `0.2.0` as the production-hardening baseline. | Matches `CHANGELOG.md` and current CI/deploy/runbook state. |
| 2026-06-09 | Use `uv run axiom serve` for local backend startup. | The repository exposes an installed CLI entry point. |
| 2026-06-12 | Add a docs index and historical-doc guide. | Keeps current docs easy to navigate without deleting audit history. |
