# AXIOM

**AXIOM Control** builds **AXIOM**: a live **company brain** — an organizational knowledge graph you can explore in 3D, fed by a real ingestion and clustering pipeline today. The long-term vision is connectors, agent skills, governance, and calibrated beliefs; those pieces are **roadmapped**, not shipped yet.

**Repo name:** AXIOM-BRAIN (repository identifier; product-facing name is AXIOM / AXIOM Control.)

---

## What's built today

These paths exist and run end-to-end in this repo:

- **Backend ingestion → SQLite → broadcast:** FastAPI service ingests events, persists entities and edges with SQLAlchemy, and publishes sequenced envelopes over WebSockets with **replay from a sequence number** (`?since=`).
- **Synthetic data sources:** A fixture-backed synthetic org plus a **live synthetic emitter** (Poisson-timed events) so the graph stays animated without external SaaS wiring.
- **Hybrid cluster classifier:** **Keyword scoring** across seven cluster vocabularies with deterministic tie-breaks; **optional Anthropic LLM fallback** only when keyword scores are weak or ambiguous (fully offline-safe when no API key — falls back to keywords / default cluster). Model is configurable in code at `HybridClassifier`.
- **Organizer loops:** Periodic classification, PageRank-style **composite importance**, and **within-cluster edge proposals** (many edges are `same_cluster_related` — structural suggestion, not curated semantics).
- **Cluster health monitoring:** Per-cluster ingest snapshots and health transitions surfaced via API and events.
- **Studio API:** Entity/edge dumps, cluster health, hybrid retrieval (lexical + semantic + graph fusion), real GitHub / Linear / Slack / Notion / Gmail connectors with OAuth state validation, webhook signature enforcement, and a Fernet-backed secrets vault.
- **Ask the Brain:** `POST /api/brain/ask` runs hybrid retrieval against the live graph, sends a grounded prompt to a stored LLM provider key (Anthropic or OpenAI from `/api/internal/llm-keys`), and returns the answer with **clickable entity citations** — the UI mounts the citations in `AskPanel` and dispatches `axiom:focus-entity` for the canvas.
- **MCP server:** Passport-gated tools (`axiom_query_brain`, `axiom_get_entity`, `axiom_traverse`, `axiom_record_action`, `axiom_check_policy`, …) with ed25519-signed receipts and a passport TTL cap.
- **Governance:** Watchdog rule engine (6 detectors), approvals workflow, agent registry, policy active-clauses API.
- **Frontend "living brain":** React + Three.js **3D graph** (hex nodes, clusters, conduits, camera motion) driven by **live REST bootstrap + WebSocket updates**, full Studio pages for Connectors, Passports, Skills, Settings, Governance, Insights, Agents, and Approvals.
- **⌘K command palette:** Debounced search wired to backend ranking (with sensible client fallback).
- **Schema & migrations:** Alembic migrations and CRUD tests around the storage layer.

**Production boundary:** Designed for **single-tenant production** behind HTTPS with `AXIOM_ENV=production` + a strong `AXIOM_API_TOKEN` (see [`docs/PRODUCTION.md`](docs/PRODUCTION.md)). Multi-tenant SaaS with per-user RBAC, managed backups, and tenant isolation are still future work.

---

## Status & roadmap

**Current focus — Phase 5.12:** Visual **Company Brain** experience — cluster layout, chrome, inspector, live stats — on top of the **real ingest + classifier + WebSocket** stack described above.

**Upcoming (roadmap — not implemented as specified here):**

| Phase | Focus |
| --- | --- |
| **6** | MCP server exposure + skills-shaped interfaces |
| **7** | **Calibra** — Bayesian belief calibration (integration lands here) |
| **8** | Skills with **real** implementations (beyond stubs) |
| **9** | Policy engine — **ALLOW / CORRECT / DENY / PAUSE** (and enforcement hooks) |
| **10** | Cryptographic receipts — **Ed25519** + **ML-DSA-65** (FIPS 204) hybrid signing (and verification path) |
| **11** | Real source connectors — Slack, GitHub, Linear, Notion, etc. |

Earlier phase checklists in older docs are superseded by **Phase 5.12** as the active rebuild track for the visual brain.

---

## Architecture

AXIOM-BRAIN is a **FastAPI** application backed by **SQLite** (configurable via SQLAlchemy **`DATABASE_URL`**) with **Alembic** migrations. Ingestion pulls from **synthetic fixtures and a timed synthetic emitter**, runs a **keyword-first classifier** with an **optional Anthropic** LLM tier for ambiguity, and broadcasts changes through an in-memory **WebSocket hub** with **sequence-based replay**. The **React + Three.js** frontend loads entities and edges from the API, subscribes to the brain socket, and renders an interactive **entity graph** with **⌘K search** backed by server-side string ranking. Nav and some footer controls are **presentational** until later phases wire routing and governance surfaces.

---

## Demo

There is **no reliable hosted demo URL** in-repo today (a previously linked site has been observed unreachable from the public internet). **Run locally:**

Backend (from repo root, after installing the package and dependencies — see project docs / `pyproject.toml`):

```bash
# Example — align with your documented entrypoint
uvicorn axiom.studio.server:app --factory --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

Open the Vite URL (typically `http://localhost:5173`). The UI expects the API at **`http://127.0.0.1:8000`** unless you configure otherwise.

For a single-origin production container, see [`docs/PRODUCTION.md`](docs/PRODUCTION.md).

---

## Configuration

Copy `.env.example` to `.env` and fill in any keys you need. Notable values:

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Optional. Enables the hybrid classifier's **optional** Anthropic LLM fallback when keyword classification is ambiguous or weak. When unset, classification stays **keyword-only** (and default cluster fallback). Provider keys for **Ask the Brain** are stored in the encrypted vault via `POST /api/internal/llm-keys` — *not* through this env var. |
| `DATABASE_URL` | SQLAlchemy URL. Defaults to `sqlite:///./axiom.db`. |
| `AXIOM_API_TOKEN` | Optional for local dev, required for deployed use. When set, non-exempt HTTP API routes require `Authorization: Bearer <token>` or `X-AXIOM-API-Key: <token>`; browser WebSockets use the `axiom.auth` subprotocol. |
| `AXIOM_AUTH_REQUIRED` | Optional fail-closed switch. Set to `1` in production so protected routes return `503` if `AXIOM_API_TOKEN` is missing. `AXIOM_ENV=production` also fails closed. |
| `AXIOM_ALLOW_WS_QUERY_TOKEN` | Disabled by default. Set only during controlled migrations to allow legacy `/ws/brain?token=<token>` auth. |
| `AXIOM_MCP_ALLOW_SYSTEM_PASSPORT` | Disabled by default. Enables demo-only MCP system passport fallback outside production. |
| `AXIOM_ALLOW_WILDCARD_PASSPORTS` | Disabled by default. Allows API-issued wildcard passport scopes only for controlled admin/development use. |
| `AXIOM_OAUTH_STATE_TTL_SECONDS` | Connector OAuth callback state lifetime. Defaults to 600 seconds and is clamped to at least 60 seconds. |
| `AXIOM_GMAIL_PUBSUB_AUDIENCE` | Required for Gmail Pub/Sub push webhooks. Must match the configured push OIDC audience. |
| `AXIOM_GMAIL_PUBSUB_SERVICE_ACCOUNT` | Optional Gmail Pub/Sub service-account email pin. When set, Gmail webhook JWTs must contain this email. |
| `AXIOM_ENV` | Set to `production` for deployed instances. Production mode disables demo simulator streams. |
| `AXIOM_VAULT_KEY` | Fernet master key for the encrypted secrets vault. Required for operations that read or write plaintext credentials, including connector OAuth/webhook secrets and access tokens. |

---

## Calibra

**Calibra** (external Bayesian calibration package) is **not** imported in early phases. Integration is planned for **Phase 7**, per the product roadmap.

---

## License

This project is licensed under the **MIT License** — see [`LICENSE`](LICENSE).
