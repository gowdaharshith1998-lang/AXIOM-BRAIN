# Changelog

All notable changes to AXIOM are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-01

Production-hardening release. AXIOM can now be deployed as a real service: the
Docker image boots with migrations, refuses to run insecurely, and survives
concurrent writers. Verified end-to-end on the production container with a
live browser session.

### Added

- **One-command production deploy**: multi-stage Dockerfile builds the SPA and
  backend into one image; the entrypoint applies Alembic migrations at boot.
  `docker compose up` gives a working, authenticated company brain.
- **Sign-in for the web app**: the SPA now ships a TokenGate — paste an API
  token once and every HTTP call and WebSocket carries your credentials
  (in-memory by default, per-tab remember option).
- **CI/CD pipelines**: GitHub Actions CI (lock-drift gate, ruff/mypy/pytest with
  coverage, frontend vitest/tsc/build, fresh-DB migration check) and a
  tag-triggered deploy workflow that builds and publishes the container image.
- **Backups & restore runbook**: online SQLite backup/restore/verify scripts, a
  compose backup service, and a documented RPO/RTO runbook in PRODUCTION.md.
- **Operational metrics**: Prometheus `/metrics` with request counters and
  latency histograms, LLM call/token counters, and background-task health
  gauges; `/livez` and `/readyz` probes for orchestrators.
- **Receipt immutability**: the governance receipt chain is now append-only at
  the database level (SQLite triggers) and signatures cover the chain linkage.
- **OAuth token refresh**: Linear and Slack connectors refresh expiring tokens
  automatically and surface a `reauth_required` status when they cannot.

### Changed

- **Security defaults are fail-closed**: API auth is required unless explicitly
  disabled for local dev; production refuses to boot without an API token,
  vault key, and signing key; the `demo_passport` backdoor is rejected in
  production.
- **Paid endpoints are protected**: Ask-the-Brain, skill runs, semantic search,
  and MCP queries all enforce rate limits, per-key concurrency caps, and daily
  token budgets reconciled against real provider usage.
- **SQLite runs in production mode**: WAL journaling, busy timeouts, and
  enforced foreign keys on every connection; Alembic is the single schema
  source with safe boot-time migration.
- **Connector syncs no longer block the server**: vendor HTTP calls run off the
  event loop with a concurrency cap; webhook ingestion is idempotent (replays
  cannot duplicate data).
- **Retrieval is bounded**: search candidate windows are importance-ordered and
  capped, edge scans are aggregated in SQL, and an optional FTS5 path is
  available behind a flag.

### Fixed

- The deployed SPA was unreachable in a browser (auth middleware returned 401
  for the app shell); static assets are now public while the API stays closed.
- Health probes (`/readyz`, `/livez`) no longer require credentials, so load
  balancers and compose healthchecks work.
- WebSockets reconnect with credentials after signing in (previously they
  retried unauthenticated forever and the UI showed OFFLINE).
- Boot migration and demo seeding now work inside containers (paths were
  resolved relative to the source tree, which breaks for pip-installed
  packages).
- Clean installs work from the lock file alone (numpy/scipy were missing as
  declared dependencies of the PageRank features).

## [0.1.0] - 2026-05-30

Initial development baseline: FastAPI ingestion/broadcast backend, SQLite
persistence, hybrid cluster classifier, organizer loops, Studio API, MCP
server, governance/policy engine, and the React + Three.js 3D brain frontend.
