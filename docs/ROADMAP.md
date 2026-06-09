# AXIOM Brain Roadmap

This is the current public roadmap for AXIOM Brain. It replaces older scratch-rebuild and pitch-era roadmap material that mixed historical plans, company context, and external research tracks.

## Naming Rules

- **AXIOM Brain** is the product in this repository.
- **AXIOM-BRAIN** is the repository slug.
- **`axiom`** is the CLI, Python package, environment-prefix, and MCP namespace.
- **AXIOM Control** is separate context and is not an alias for AXIOM Brain.
- **company brain** is category language, not a second product name.

## Current Product Boundary

AXIOM Brain is currently a single-tenant company-knowledge-graph application. It can be run locally, tested in CI, and deployed as a controlled single-tenant service when the production runbook is followed.

The current system includes:

- FastAPI backend and Studio API.
- SQLite graph storage with Alembic migrations.
- Synthetic ingestion and live synthetic event stream.
- React + Three.js Studio frontend.
- Search, entity inspection, graph events, and Ask the Brain.
- Connector surfaces and encrypted provider/connector vault.
- Governance primitives: passports, policies, approvals, watchdog checks, receipts, and MCP tools.
- Docker, Compose, CI, CodeQL, backup, restore, health, readiness, and metrics scaffolding.

The current system does not yet include:

- Managed multi-tenant hosting.
- Per-user identity and tenant isolation.
- Admin RBAC.
- Managed Postgres or hosted database infrastructure.
- Full production observability.
- Proven real-workspace rollout across all connector types.

## Roadmap Priorities

### 1. Public Repository Clarity

Status: active

- Keep README, phases, and roadmap consistent with AXIOM Brain naming.
- Keep historical audit and design documents labeled as historical when they are not current truth.
- Keep setup, test, build, and deployment commands aligned with CI.
- Keep community health files current.

### 2. Frontend Architecture

Status: active

- Split the app shell from route configuration, navigation icons, and product constants.
- Continue extracting the 3D brain renderer into focused modules.
- Segment large global CSS into smaller style files once component ownership is clear.
- Preserve routes, auth behavior, WebSocket behavior, and current graph visuals while refactoring.

### 3. Backend Architecture

Status: active

- Continue router extraction from `src/axiom/studio/server.py`.
- Keep `create_app()` as the public app assembly point.
- Move endpoint groups into focused modules for connectors, skills, governance, health, and metrics.
- Keep schema, route paths, auth, vault plaintext discipline, and MCP tool names stable.

### 4. Connector Reliability

Status: ongoing

- Improve source sync reliability and error reporting.
- Keep OAuth state validation and webhook signature verification strict.
- Continue vendor-specific tests for GitHub, Linear, Slack, Notion, and Gmail flows.
- Make real-account verification repeatable without committing credentials.

### 5. Governance And Agent Operations

Status: ongoing

- Strengthen policy evaluation and approval flows.
- Continue signed receipt validation and receipt-chain checks.
- Expand MCP coverage while preserving passport and scope enforcement.
- Keep demo-only fallbacks disabled in production.

### 6. Production Readiness

Status: ongoing

- Keep production startup fail-closed.
- Keep backups and restore checks documented and testable.
- Keep `/livez`, `/readyz`, and `/metrics` deployment-friendly.
- Add operational dashboards and alerting outside the repo when a deployment target is chosen.

### 7. SaaS Readiness

Status: planned

- Add identity and tenant models.
- Add per-user RBAC.
- Move toward managed database and tenant-isolated infrastructure.
- Define hosted-product boundaries separately from the open repository.

## Refactor Guardrails

- Do not rename the `axiom` package, CLI, environment prefix, or MCP tools in a broad cleanup.
- Do not rewrite migrations or schema history without a dedicated migration plan.
- Do not change auth, vault, receipt, policy, WebSocket, or MCP behavior without targeted characterization tests.
- Do not remove historical audit documents just because they contain old assumptions.
- Do not turn reserved schema fields into public product claims.

## Current Verification Set

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
