# AXIOM Brain

AXIOM Brain is a company knowledge graph that turns organizational activity into a live, searchable, governable 3D brain for operators and AI agents.

This repository contains **AXIOM Brain**. `AXIOM-BRAIN` is the GitHub/repository slug. `axiom` is the Python package, CLI, environment-prefix, and MCP tool namespace. **AXIOM Control is a separate product/company context, not an alias for this repo.**

## Current Status

AXIOM Brain is a working single-tenant application for local development and controlled deployment. It has a FastAPI backend, SQLite graph storage, Alembic migrations, a React/Three.js Studio frontend, graph search, connector surfaces, an encrypted vault, governance primitives, signed receipts, and an MCP server.

It is not a managed multi-tenant SaaS yet. Per-user identity, tenant isolation, admin RBAC, managed database infrastructure, and production observability remain roadmap work.

There is no maintained hosted demo URL in this repository. Run the app locally or deploy it as a single-tenant service with the production controls in `docs/PRODUCTION.md`.

## What Works Today

- Ingests synthetic company events into a SQLite entity/edge graph.
- Persists entities, edges, clusters, receipts, policies, passports, approvals, connector metadata, and encrypted vault references.
- Runs a FastAPI Studio API with REST endpoints and a WebSocket brain stream.
- Replays graph events from a sequence number so reconnecting clients can catch up.
- Classifies graph entities with deterministic keyword scoring and optional Anthropic fallback for ambiguous cases.
- Computes composite importance and proposes within-cluster relationships.
- Serves a React + Vite + Three.js Studio frontend with a live 3D graph.
- Supports graph search, entity inspection, connectors, governance, agents, approvals, insights, skills, settings, and command-palette flows.
- Provides Ask the Brain through stored Anthropic or OpenAI provider keys in the encrypted vault.
- Exposes an MCP stdio server with passport-gated tools and signed action receipts.
- Includes Docker, Compose, health checks, metrics, backup/restore scripts, and GitHub Actions CI.

## Demo

Start the backend:

```bash
uv sync --frozen --extra dev
uv run axiom serve --host 127.0.0.1 --port 8000 --live
```

Start the frontend in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the Vite URL, usually `http://localhost:5173`. During local development the frontend expects the API at `http://127.0.0.1:8000`.

## Tech Stack

| Area | Stack |
| --- | --- |
| Backend | Python 3.13, FastAPI, Uvicorn, Pydantic |
| Storage | SQLite, SQLAlchemy, Alembic |
| Frontend | React 18, Vite, TypeScript, Three.js, Zustand |
| Testing | pytest, pytest-cov, Vitest, Testing Library |
| Quality | Ruff, mypy, TypeScript type checking |
| Operations | Docker, Docker Compose, Prometheus metrics, GitHub Actions |
| Integrations | GitHub, Linear, Slack, Notion, Gmail, Anthropic/OpenAI provider-key flows |

## Repository Map

```text
.
+-- src/axiom/          FastAPI app, storage, ingest, governance, MCP, connectors
+-- frontend/           React, Vite, TypeScript, and Three.js Studio UI
+-- tests/              Backend pytest suite
+-- alembic/            Database migrations
+-- docs/               Production, connectors, policies, phases, audits, and specs
+-- fixtures/           Synthetic company data
+-- policies/           Starter policy pack
+-- scripts/            Backup, restore, verification, and helper scripts
+-- .github/            CI, CodeQL, deploy workflow, issue templates, PR template
```

## Getting Started

### Prerequisites

- Python 3.13
- `uv`
- Node.js 22
- npm

### Backend

```bash
uv sync --frozen --extra dev
uv run axiom serve --host 127.0.0.1 --port 8000
```

Run with the live synthetic event stream:

```bash
uv run axiom serve --host 127.0.0.1 --port 8000 --live
```

Run one synthetic ingest pass:

```bash
uv run axiom ingest --source synthetic
```

Run the MCP server over stdio:

```bash
uv run axiom mcp-serve --api-base-url http://127.0.0.1:8000
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Configuration

Copy `.env.example` to `.env` and set only the values needed for your local or deployment target.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL. Defaults to `sqlite:///./axiom.db`. |
| `AXIOM_ENV` | Set to `production` for deployed instances. Production mode disables demo simulator streams. |
| `AXIOM_API_TOKEN` | Bearer token for protected API routes. Optional in local development, required for production. |
| `AXIOM_AUTH_REQUIRED` | Set to `1` to fail closed when `AXIOM_API_TOKEN` is missing. |
| `AXIOM_VAULT_KEY` | Fernet master key for encrypted connector and provider secrets. Generate with `uv run axiom vault init`. |
| `ANTHROPIC_API_KEY` | Optional classifier fallback key for ambiguous cluster classification. Ask the Brain provider keys are stored through the vault API instead. |
| `AXIOM_ALLOW_WS_QUERY_TOKEN` | Legacy WebSocket query-token support. Keep disabled except during controlled migrations. |
| `AXIOM_MCP_ALLOW_SYSTEM_PASSPORT` | Demo-only MCP system passport fallback. Keep disabled in production. |
| `AXIOM_ALLOW_WILDCARD_PASSPORTS` | Allows wildcard passport scopes for controlled admin/development use. |
| `AXIOM_GMAIL_PUBSUB_AUDIENCE` | Required when Gmail Pub/Sub push webhooks are enabled. |
| `AXIOM_GMAIL_PUBSUB_SERVICE_ACCOUNT` | Optional service-account email pin for Gmail Pub/Sub webhook JWTs. |

Vault status:

```bash
uv run axiom vault status
```

Generate a new vault key:

```bash
uv run axiom vault init
```

Keep the vault key secret. Losing it makes stored connector and provider secrets unreadable.

## Development Checks

Backend:

```bash
uv lock --check
uv sync --frozen --extra dev
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv run mypy
uv run pytest -q --maxfail=5 --cov=axiom --cov-report=xml --cov-fail-under=50
uv run alembic upgrade head
```

Frontend:

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
```

## Production Boundary

AXIOM Brain can run as a single-tenant production service when these controls are configured:

- HTTPS termination
- `AXIOM_ENV=production`
- `AXIOM_AUTH_REQUIRED=1`
- strong `AXIOM_API_TOKEN`
- configured `AXIOM_VAULT_KEY`
- scheduled SQLite backups
- WebSocket auth through the `axiom.auth` subprotocol
- demo-only fallbacks disabled

Build and run with Docker:

```bash
docker build -t axiom-brain .
docker run --env-file .env -p 8000:8000 axiom-brain
```

Or with Compose:

```bash
AXIOM_API_TOKEN=<token> docker compose up --build
```

See [docs/PRODUCTION.md](docs/PRODUCTION.md) for the full runbook.

## Project Phases

| Phase | Status | Focus |
| --- | --- | --- |
| 1 | Complete | Foundation: package, backend, frontend, graph model, migrations, and CI skeleton. |
| 2 | Complete | Production hardening: Docker, boot migrations, auth defaults, SQLite reliability, vault, backups, and health checks. |
| 3 | In progress | Public repository surface: README, contributor docs, security policy, templates, CodeQL, and naming clarity. |
| 4 | Active | AXIOM Brain experience: graph layout, inspector, live stats, search, and real-time visual interactions. |
| 5 | Ongoing | Governance, skills, connectors, passports, policies, receipts, approvals, and MCP workflows. |
| 6 | Planned | SaaS readiness: identity, tenant isolation, RBAC, managed infrastructure, and deeper observability. |

See [docs/PHASES.md](docs/PHASES.md) for expanded phase notes.

## Useful Documentation

- [Production runbook](docs/PRODUCTION.md)
- [Project phases](docs/PHASES.md)
- [Current roadmap](docs/ROADMAP.md)
- [Connector guide](docs/CONNECTORS.md)
- [Policy guide](docs/POLICIES.md)
- [Skills guide](docs/SKILLS.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

Historical design and audit docs are preserved for context, but the README, `docs/PHASES.md`, and `docs/ROADMAP.md` are the current public orientation docs.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Keep changes scoped, run the relevant checks, and document any behavior or operational changes.

## Security

Do not report suspected vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md) for private reporting guidance and supported-version expectations.

## License

AXIOM Brain is licensed under the MIT License. See [LICENSE](LICENSE).
