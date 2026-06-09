# AXIOM Project Phases

This file summarizes the active project state for visitors and contributors. Older phase checklists in audit or rebuild documents are historical unless explicitly referenced here.

## Phase 1: Foundation

Status: Complete

- Established the Python package, FastAPI backend, React/Vite frontend, SQLite storage, Alembic migrations, and CI skeleton.
- Added the universal entity/edge model and synthetic source fixtures.
- Created the first Studio API and 3D visual brain surface.

## Phase 2: Production Hardening

Status: Complete as of `0.2.0`

- Added Docker and Compose production paths.
- Added boot-time Alembic migration support.
- Hardened auth defaults for production.
- Added SQLite WAL/busy-timeout/foreign-key setup.
- Added encrypted vault handling for connector and provider secrets.
- Added CI lockfile, lint, type, test, migration, and frontend build gates.
- Added backup, restore, and health-check runbooks.

## Phase 3: Professional Repository Surface

Status: In progress

- Align README setup commands with the installed CLI and CI workflow.
- Add contributor, security, code-of-conduct, issue-template, and pull-request-template files.
- Add CodeQL workflow coverage for Python and TypeScript/JavaScript.
- Keep project docs honest about what is shipped, what is roadmapped, and what is operationally required.

## Phase 4: Company Brain Experience

Status: Active product track

- Continue the visual Company Brain work: cluster layout, chrome, inspector, live stats, and search interactions.
- Keep the frontend wired to real REST bootstrap and WebSocket updates.
- Verify major visual changes with tests and browser checks.

## Phase 5: Governance, Skills, And Connectors

Status: Ongoing

- Expand connector reliability and source sync.
- Continue governance, passport, policy, receipt, and approval surfaces.
- Harden SkillFiles and MCP workflows around real storage and signed receipts.
- Preserve the production boundary: single-tenant, HTTPS, strong API token, configured vault, and scheduled SQLite backups.

## Phase 6: Future SaaS Readiness

Status: Planned

- Add per-user identity and tenant isolation.
- Move from single-tenant operational assumptions to managed multi-tenant infrastructure.
- Add admin RBAC, audit identity, managed database strategy, and deeper observability.

## Decision Log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-06-09 | Keep AXIOM as the product name and AXIOM-BRAIN as the repository identifier. | Matches existing README naming convention and avoids product/repo confusion. |
| 2026-06-09 | Treat `0.2.0` as the current production-hardening baseline. | Matches `CHANGELOG.md` and current CI/deploy/runbook state. |
| 2026-06-09 | Use `uv run axiom serve` for local backend startup. | The repository has a CLI module and now exposes it as an installed console script. |
