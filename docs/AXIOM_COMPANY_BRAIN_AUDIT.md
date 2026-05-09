# AXIOM Company Brain Audit

**Scope:** Repository-grounded architecture audit for a governed, source-backed company intelligence layer **inside this codebase** (`AXIOM-BRAIN`).  
**Date:** 2026-05-07  
**MCP tooling:** Ruflo `analyze_file-risk` was run on representative backend files (high risk flagged for large `schema/models.py` changes; `studio/server.py` assessed low for moderate route additions). Ruflo `guidance_discover` confirmed local skill inventory (informational).

---

## Executive Summary

**What AXIOM already is (this repo):** A **single-tenant** FastAPI “Studio” API + **Vite/React** frontend with a **live 3D “Company Brain”** (`Brain.tsx`) backed by **SQLAlchemy models** `Source`, `Entity`, `Edge`, plus `Action`, `Receipt`, `Skill`. Data defaults to **SQLite** (`DATABASE_URL` / `sqlite:///./axiom.db`). **Alembic** migrations exist. Real-time updates use an in-process **`EventBroadcaster`** and **`/ws/brain`**. Keyword entity search is **Python-side** (Levenshtein-style), not DB FTS. **Governance is largely synthetic/demo**: `SyntheticPolicyEvaluator`, `synthetic_receipt`, periodic `emit_agent_actions` / `emit_warden_insights` — not a production RBAC or policy-authority service.

**Critical honesty:** The audit prompt assumes **Next.js App Router**, **Postgres/pgvector**, **project-scoped multi-tenancy**, `PolicyProfileVersion`, and **existing enterprise auth**. **None of that exists in this repository today.** Building the “Company Brain” **must** align with **actual** patterns here or you will ship conflicting architecture. The design direction in `DESIGN.md` (7 entity types, governance, Calibra, MCP) is **aspirational**; implementation is **partial**.

**Strongest reuse (do not duplicate):** The **graph substrate is already `Entity` + `Edge` + `Source`**. “Brain nodes” should **not** be a parallel `BrainNode` table in V1 unless you have a hard requirement those rows cannot live in `entities`. Prefer **`entity.type`** (string) and **`entity.data` JSON** for domain-specific fields (trust, authority, provenance), consistent with `EntityDTO` and `DESIGN.md` metadata contracts. **Edges** already model relationships; use **`relationship`** for edge kinds (`SUPPORTS`, `GOVERNS`, …) with optional `data` for weights and citations.

**Where it should live:** **Conceptually** the product already centers the brain: `App.tsx` renders `Brain` full canvas. **URL routing** is not Next.js — there is **no `/projects/[id]`** tree. A first “Brain V1” surface should extend **existing layout** (`SourcesRail`, `InspectorPanel`, `CommandPalette`, `BottomToolbar`) rather than inventing a second app shell. **APIs** should follow **`/api/...`** (not `/projects/...` until a `Project` model exists).

**Safest phased plan:** (0) This audit. (1) **Conventions + CRUD + audit hooks** on existing tables; optional thin tables only for **embeddings** or **query logs** if you must index separately. (2) **UI modes** (filters, drawer fields, roadmap/decision views) on current Three.js canvas. (3) **Traversal + keyword** APIs (NetworkX is already a dependency). (4) **Claims + trust UI** in `entity.data`. (5) **Mapping views** (YC → roadmap chains) as derived queries, not new core types. (6) **Agent preflight** HTTP endpoint returning structured context (warn-only). (7) **Semantic search** only after **Postgres + pgvector** (or external vector store) is an explicit platform decision — **not** in SQLite V1.

---

## Current Architecture Findings

### Backend app structure

| Area | Location | Notes |
|------|----------|--------|
| Package root | `src/axiom/` | Main Python package |
| HTTP app | `src/axiom/studio/server.py` | `create_app()` builds FastAPI, CORS to Vite dev ports, **no auth dependencies** |
| CLI | `src/axiom/cli.py` | `axiom ingest`, `axiom serve` |
| API modules | `src/axiom/api/search.py` | Entity search |
| Schema | `src/axiom/schema/models.py`, `dto.py` | SQLAlchemy + Pydantic DTOs |
| Storage | `src/axiom/storage/db.py`, `crud.py` | Engine/session helpers |
| Ingest | `src/axiom/ingest/` | Pipeline, broadcaster |
| Governance | `src/axiom/govern/` | Synthetic policy, ledger stubs, warden |
| Organize | `src/axiom/organize/` | Classifier, centrality, edge proposer, **OrganizerAgent** background loops |
| Policy (interfaces) | `src/axiom/policy/interfaces.py` | Stubs for future engine |

**Patterns:** Sync SQLAlchemy sessions inside route handlers; **async** only for WebSocket and background tasks. **`EventBroadcaster`** buffers last **1000** events in memory (`ingest/broadcaster.py`).

**Risks if Company Brain touches this:** Route bloat in `server.py`; need **router modules** before adding many endpoints. Any **persistent audit** must not rely solely on the broadcaster buffer.

### Frontend app structure

| Area | Location | Notes |
|------|----------|--------|
| Entry | `frontend/src/main.tsx`, `App.tsx` | Single-page shell |
| Brain visualization | `frontend/src/components/Brain.tsx` | **Three.js** + instanced meshes, hex layout, WebSocket |
| State | `frontend/src/state/brain.store.ts` | Zustand: entities, edges, cluster health, synthetic agent actions, receipts, insights |
| Inspector | `frontend/src/components/InspectorPanel.tsx` | Entity/cluster detail; some **static marketing copy** in default view |
| Layout libs | `frontend/src/lib/cluster-layout.ts`, `hex-layout.ts`, `hex-geometry.ts` | Seven canonical **cluster IDs** |
| Styling | Tailwind (`tailwind.config.ts`); **no shadcn** in `package.json` | |

**Patterns:** `fetch('/api/entities')`, `fetch('/api/edges')`, `BrainSocket` for `/ws/brain`. **No React Router** in `package.json` — navigation is not multi-route today.

**Risks:** Adding a second graph library “for layout” without reconciling the Three.js scene will split UX. Prefer **extending** the existing canvas.

### Database models

Defined in `src/axiom/schema/models.py` (see also initial migration `alembic/versions/309b33ebec31_initial_schema.py` and `a1b2c3d4e5f6_add_cluster_id_and_importance.py`):

- **`sources`**: connector metadata.
- **`entities`**: `type` (free text), `data` JSON, `source_id`, `cluster_id`, `composite_importance`.
- **`edges`**: `source_id`/`target_id` → **entities**, `relationship`, `data`.
- **`receipts`**: Merkle-ish fields + signatures (placeholders).
- **`actions`**: Agent action records (schema present; population is synthetic in demos).
- **`skills`**: Emitted skills linked to `process_entity_id`.

**Pattern:** UUIDv7-style hex IDs via `new_id()`.

**Risks:** `Entity.type` is **not** constrained to the seven types in `DESIGN.md` — flexibility is good for brain node kinds if you **namespace** values (e.g. `brain.vision`, `axiom.document`).

### Alembic migration pattern

- Config: `alembic.ini`, `alembic/env.py`, revisions under `alembic/versions/`.
- Tests: `tests/test_migrations.py` exercises upgrade → downgrade → upgrade on SQLite temp DB.

**Pattern:** SQLite-compatible `op.add_column` / `create_table`; second migration adds entity columns with server default for importance.

**Risks:** Data **seeding** should **not** be committed as Alembic data migrations for product content — use **scripts** or **admin API** (see Seed Strategy).

### Auth / session / project isolation

**Current state:** **No authentication**, **no `Project` model**, **no org/workspace** in schema. CORS allows local Vite origins. **All API routes are open** to any caller that can reach the server.

**Implication:** Any “Company Brain” holding **real** strategy or customer data **must not ship** without an **auth + tenancy design** decided elsewhere or added here first. The audit’s `brain:*` permissions are **forward-looking** — map them when RBAC exists.

### Service patterns

- **In-process** background work: `OrganizerAgent` + `ClusterHealthMonitor` + synthetic governance loops in FastAPI **lifespan** (`studio/server.py`).
- **No Redis/Celery** in `pyproject.toml` — async **asyncio** tasks, not a distributed queue.

### Audit / event logging

- **Runtime events:** `EventBroadcaster` with `seq`, **not** durable audit log.
- **Receipts table:** exists for signed artifacts; **synthetic** payloads in demo paths (`govern/ledger.py`).
- **Actions table:** available for persisting real agent actions when wired.

**Gap:** No append-only **audited Company Brain mutation log** — use `receipts` with a dedicated `receipt_type` and structured `payload`, or add **`brain_audit_events`** table in a later phase.

### Policy / governance

- **File:** `policies/intelligent.yaml` — placeholder “allow *” style.
- **Code:** `SyntheticPolicyEvaluator` — random deny / special case; **not** connected to `policies/intelligent.yaml` parsing in the snippets reviewed.
- **`DESIGN.md`:** Full policy semantics documented for **future** phases.

**Risks:** Do not implement “Company Brain policy authority” as a second policy engine. **Link** brain nodes to **YAML version / hash** in metadata when a real evaluator exists.

### Agent / job / run system

- **Synthetic stream:** `emit_agent_actions` publishes WebSocket events; frontend logs in `brain.store`.
- **No** “run inspector” database model named `AgentRun` — closest is **`actions`** + **events**.

### Worker / queue

- **Background:** Organizer + health + synthetic emitters — **no** separate worker process.

### UI routing / theme

- **Single view**; dark theme tokens inline (e.g. `bg-[#05050a]`, `border-white/10`).
- **Reusable:** `InspectorPanel` entity detail pattern, `CommandPalette` for search affordance.

### API client patterns

- Plain **`fetch`** in `Brain.tsx` and tests; no generated OpenAPI client.

### Test structure

- **`tests/`** pytest: migrations, search API, organizer, ingest, server smoke (`test_server_phase_3.py`), etc.
- **Frontend:** Vitest under `frontend/src/__tests__/`.

---

## Existing Systems to Reuse

| Capability | Reuse |
|------------|--------|
| Graph storage | **`entities` + `edges` + `sources`** |
| Node typing | **`Entity.type` + `data`** (add `brain_*` or namespaced keys) |
| Relationships | **`Edge.relationship` + `Edge.data`** |
| Real-time UI | **`/ws/brain` + `EventBroadcaster`** |
| Keyword search | **`search_entities()`** in `api/search.py` — extend or add `/api/brain/search` wrapping same + graph scoring |
| Graph algorithms | **`networkx`** (`pyproject.toml`) — server-side traversal for preflight |
| Signatures / audit trail | **`receipts`** table for governance-style records when payload defined |
| Clustering UX | **`cluster_id` + seven `CLUSTER_IDS`** in `cluster-layout.ts` — map brain “domains” to clusters or add eighth cluster only with UI + migration discipline |
| 3D brain UI | **`Brain.tsx`** — keep as primary “graph canvas” |

**Avoid:** Parallel `BrainNode` / `BrainEdge` tables until hard requirements (e.g. separate lifecycle or permissions per table) justify the migration cost. Ruflo **file-risk** flagged **high** touch risk for `models.py` — prefer **additive** migrations and **JSON contracts** first.

---

## Integration Map

### Governance / policy

**Connect by reference, not duplication:** Store on entity/edge JSON:

- `data.policy_pack_id` / `data.policy_yaml_hash`
- `data.canonical_clause_id` (when engine exists)

Brain answers “why this policy exists” via **edges** `DERIVED_FROM` / `EVIDENCED_BY` to **document** entities (`type: document`, `doc_type: policy` per `DESIGN.md`).

### Agent runs / execution

- Persist important runs in **`actions`** (or future `agent_runs` if you outgrow schema).
- Link graph: **edges** from `code` / `process` entities to **actions** or external run IDs in `data`.

### Audit / timeline

- **Mutations:** insert **`receipts`** or dedicated audit rows; emit **WebSocket** event for UI.
- **Query logging:** new table recommended (`brain_query_log`) — not present today.

### Projects / multi-tenant isolation

**Today:** single database — **project_id must be future**. Optional approach: add nullable `project_id` on `entities`/`sources` in a **later** migration when auth exists; until then **operate as single-org** and **do not** pretend isolation in API.

---

## Proposed Domain Model

**Pragmatic mapping (recommended V1):**

| Concept | Implementation |
|---------|----------------|
| BrainSource | Reuse **`Source`** row; distinguish `source_type` (e.g. `brain.manual`, `brain.ingestion`, `linear`, …) |
| BrainNode | Reuse **`Entity`** with `type` ∈ documented set (`vision`, `roadmap_item`, … or namespaced `brain.vision`) |
| BrainEdge | Reuse **`Edge`** with constrained `relationship` strings |
| BrainClaim | **`Entity`** with `type: claim` or subtree in `data.claims[]` — prefer dedicated **claim entities** for traceability |
| BrainDecision | Align with **`DESIGN.md` `decision`** type fields inside `entity.data` |
| BrainQuery | Persist as **`brain_query_log`** table (Phase 3+) |
| BrainAuditEvent | **`receipts`** with `receipt_type: brain.*` **or** new table if query volume dominates |
| BrainEmbedding | New table **`entity_embeddings`** (entity_id FK, model, dim, vector blob) **when** vector search is approved — **not** for SQLite long-term at scale |
| BrainIngestionJob | No Celery — use **`sources.metadata`** + job row **or** reuse **ingest pipeline** patterns in `ingest/` |

**Node types (minimum):** Implement as **allowed `Entity.type` values** (document in code + OpenAPI). Examples: `vision`, `roadmap`, `feature`, `decision`, `policy_doc`, `customer_signal`, `problem`, `risk`, `agent`, `run`, `incident`, `code_area`, `research`, `yc_advice`, `architecture_rule`, `blocker`, `milestone`.

**Edge types:** Validate in application layer: `SUPPORTS`, `DEPENDS_ON`, `CONTRADICTS`, `IMPLEMENTS`, `BLOCKS`, `DERIVED_FROM`, `APPROVED_BY`, `RELATED_TO`, `SUPERSEDES`, `EVIDENCED_BY`, `GOVERNS`, `AFFECTS`, `USED_BY`, `MENTIONS`.

**Indexes:** Existing `(type)`, `(cluster_id)`, composite `(type, created_at)`. Add **partial** or **composite** indexes when query patterns clear (e.g. `(type, updated_at)`).

---

## Proposed Database Schema

**Phase 1 (minimal, additive):**

1. **No new tables** — only JSON schema discipline + optional constraints in Pydantic.
2. Optional: **`brain_query_log`** when `/api/brain/query` ships:
   - `id`, `created_at`, `actor` (nullable), `query_text`, `response_meta` JSON, `duration_ms`, `project_id` (nullable future).

**Phase 2+ (when needed):**

- **`entity_embeddings`**: FK `entities.id`, `provider`, `model`, `vector` (bytea / BLOB) — **Postgres migration** likely required for pgvector.

**Migration / rollback:** Follow existing Alembic style; test upgrade/downgrade (`test_migrations.py`). **Rollback:** drop new tables/columns; embeddings regeneration from source text.

**Risk level:** Extending JSON — **low**; new tables — **medium**; pgvector — **high** (infra + ops).

---

## Proposed Backend APIs

**Adapted to this repo:** Prefix **`/api/brain/...`** (not `/projects/{id}/...` until models exist). All routes **future-auth**: `Depends(require_project_read)` placeholder.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/brain/health` | Brain subsystem + index stats (optional) |
| GET/POST | `/api/entities`, `/api/edges` | **Already exist** — extend with filters query params before duplicating |
| GET | `/api/brain/nodes` | Filtered entities (`type`, `cluster_id`, trust, date) |
| POST | `/api/brain/nodes` | Create entity (validate type/JSON) |
| GET/PATCH | `/api/brain/nodes/{id}` | Read/update with optimistic concurrency (`updated_at`) |
| GET/POST | `/api/brain/edges` | Create/list edges with relationship validation |
| POST | `/api/brain/query` | Structured query: keyword + optional hop depth (NetworkX) |
| POST | `/api/brain/ingest` | Upload/source attach (writes `Source` + entities) — **auth-gated** later |
| GET | `/api/brain/graph` | Subgraph export (nodes + edges) for canvas |
| GET | `/api/brain/roadmap-map` | Precompiled chain or BFS from `yc_advice` / `vision` seeds |
| POST | `/api/brain/agent-preflight` | Target action descriptor → context bundle + warnings |

**Auth:** Today: **none**. **Target:** API keys or session + RBAC; **project filter** on queries when `project_id` column exists.

**Audit:** On mutating routes, write **`receipts`** or `brain_query_log` as designed.

**Errors:** 400 validation, 404 missing node, 409 conflict on update; 401/403 when auth lands.

**Tests:** Mirror `tests/test_search_api.py` — isolation tests **after** tenancy.

---

## Proposed Frontend UI

**First implementation locations (concrete):**

| Piece | Suggested path |
|-------|----------------|
| Brain filters / trust toggles | Extend **`InspectorPanel.tsx`** or new `BrainFiltersBar.tsx` imported from **`App.tsx`** |
| Node drawer richness | **`InspectorPanel.tsx`** — add sections: trust, sources, edges list, audit |
| “Roadmap mode” / “Preflight mode” | **`BottomToolbar.tsx`** or **`CommandPalette.tsx`** mode switch; state in **`brain.store.ts`** |
| Data loading | Existing bootstrap in **`Brain.tsx`** — ensure modes call `/api/brain/graph` |
| Empty/error | Centralize in inspector or overlay component next to **`Brain`** |

**Do not** add a fake static graph for MVP — **seed real rows** in dev (see Seed Strategy).

**Graph library:** **Keep Three.js** (`Brain.tsx`). It already delivers hex/cluster aesthetic. For **2D minimap** or editor-only view, optional **React Flow** later — **not** V1 if it duplicates the main canvas.

---

## Proposed Graph Visualization Approach

**Recommendation for V1:** **Stay on Three.js** (current stack: `three` in `package.json`, custom hex layout, instancing, conduits).

| Criterion | Three.js (current) | React Flow | Sigma / Cytoscape | D3 | R3F |
|-----------|---------------------|------------|-------------------|----|----- |
| Next.js App Router | N/A (Vite) | OK | OK | OK | OK |
| Performance MVP | Good (instancing) | Good | Good | Manual | Good |
| Custom nodes | Full control | Strong | Good | Full | Full |
| Drawer integration | Already wired | OK | OK | OK | OK |
| Hex/brain visual | **Already built** | Build from scratch | Build | Build | Build |
| Integration risk | **Lowest** — zero new deps | Medium new surface | Medium | High | Medium (refactor to R3F) |

---

## Source-Backed Truth Model

**Fields (live in `Entity.data` and optional `Edge.data`):**

- `trust_level`: `CANONICAL` | `APPROVED` | `SOURCE_BACKED` | `INFERRED` | `DRAFT` | `DEPRECATED` | `CONFLICTED`
- `authority_rank` (ordinal) — aligns with prompt: canonical policy > active roadmap > approved decision > note > brainstorm
- `confidence` ∈ [0,1] — parallel to `DESIGN.md` Calibra fields when integrated
- `source_ids` — list of `sources.id`; **primary citation** required for `SOURCE_BACKED` and above
- `created_by`, `last_verified_at`, `supersedes_entity_id`

**Enforcement:**

- **API validation** on create/update (Pydantic).
- **UI** badges in `InspectorPanel`.
- **`receipts`** or audit table on promotion to `CANONICAL` / `DEPRECATED`.

**Where logged:** Receipts + future `brain_query_log` for retrieval operations by agents.

---

## Query and Retrieval Architecture

**Capabilities roadmap:**

| Layer | MVP | Later |
|-------|-----|-------|
| Keyword | ✅ `search_entities` + `/api/brain/query` wrapping | Postgres FTS / tsvector |
| Semantic | ❌ Not in repo | pgvector **or** external AgentDB/embeddings API |
| Graph traversal | ✅ NetworkX in API | Optimize hot paths + indexes |
| Source lookup | ✅ by `source_id` | Full-text on stored blobs when content store exists |

**Verification:** **`pyproject.toml` has no `pgvector`/embedding dependency.** DESIGN mentions cosine **for future policy drift**, not implemented as storage.

**Least risky semantic path:** **External** embedding service + optional **`entity_embeddings`** table after Postgres adoption; avoid bolting vectors onto SQLite beyond a tiny prototype.

**Streaming:** WebSocket exists for **events**, not for LLM streams — add SSE/WS **only** if “Ask the Brain” uses an LLM.

---

## Agent Preflight Architecture

**V1 behavior:** **Retrieve + warn** — no blocking unless `trust_level` / future policy engine returns hard deny.

**Request (example):**

```json
{
  "target": { "kind": "code_area", "id": "ent_...", "intent": "modify" },
  "tooling": { "agent": "cursor", "task_id": "optional" }
}
```

**Response:** Bundles: related **policies** (document entities), **decisions**, **incidents** (ticket/thread types), **architecture_rule** entities, **risks**, **roadmap** nodes — each with **IDs for graph navigation** and **trust/confidence**.

**Logging:** **`brain_query_log`** rows: actor, latency, result size, **no raw secrets** by default.

**Performance:** Preflight **must** bound work: max hops, max nodes, timeouts; cache **hot** policy docs in memory when safe.

**Policy tie-in:** Return **`policy_yaml_hash`** and **evaluation** stub until real engine wired.

---

## Security and Permissions

**Current state:** **Open API** — treat as **dev-only**.

**Proposed permission strings (future):**

| Permission | Meaning |
|------------|---------|
| `brain:read` | Read graph |
| `brain:write` | Create/update entities/edges |
| `brain:ingest` | Run ingestion |
| `brain:approve` | Promote trust / canonical |
| `brain:query` | Query endpoint (audit) |
| `brain:agent_preflight` | Machine-oriented read |
| `brain:audit_read` | Read audit logs |

**Map to roles** when IAM exists. **External agents:** read-only + query log; **never** expose raw customer PII in brain without redaction.

**Encryption:** At-rest DB encryption is **deployment** concern; **field-level** for highly sensitive notes in `data`.

---

## Build Phases

| Phase | Goal | Backend | Frontend | DB | Tests | Risks | Done when |
|-------|------|---------|----------|-----|-------|-------|-----------|
| **0** | Audit | — | — | — | — | — | This document approved |
| **1** | Foundation | CRUD routes + validation; optional `brain_query_log` | Drawer fields for trust/source | Additive Alembic only if new table | API + migration tests | Schema sprawl | CRUD works + WS updates |
| **2** | Visual V1 | `/api/brain/graph` | Filters + modes + real seed | Seeds via script | Vitest smoke | UX complexity | Data-backed graph |
| **3** | Queryable | NetworkX traversal + keyword | Query panel | — | Traversal tests | Performance | Bounded subgraph API |
| **4** | Claims | Claim entities + validation | Evidence UI | — | Claim tests | Trust misuse | Claims trace to sources |
| **5** | Roadmap / YC | Chain endpoints | Chain view | — | Snapshot tests | Overfitting data | Chain renders |
| **6** | Preflight | `/api/brain/agent-preflight` | Dev-only panel | Query log | Isolation tests **post-tenancy** | Latency | Warn-only bundle |
| **7** | Semantic | Embeddings pipeline | — | Postgres/pgvector likely | Recall eval | Ops | Retrieval quality baseline |
| **8** | Governed | Approval for CANONICAL; policy hash lock | Approver UI | Receipts | E2E | Policy conflict | Enforced promotions only when policy requires |

---

## Test Plan

**Backend:** Node/edge CRUD; relationship enum validation; project isolation **placeholder skipped until tenancy**; preflight bounds; audit/receipt write; migration up/down.

**Frontend:** Brain renders; graph fetch; drawer; filters; loading/error; unauthorized **skip until auth**.

**Integration:** WebSocket client receives updates after POST entity; **cross-project** tests **N/A** today.

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| Schema complexity | JSON-first; tables only when necessary |
| Graph query performance | Limits, indexing, prefetch subgraphs |
| Permission leakage | **Do not** deploy sensitive data until auth + `project_id` |
| AI hallucination | No unsourced generative answers in UI; retrieval-only V1 |
| Source trust misuse | Explicit `trust_level` + approval flow for CANONICAL |
| UX complexity | Modes rollout incrementally |
| Migration failure | Alembic tests + backups |
| Governance conflict | Single policy evaluator vision; brain links by reference |
| Over-enforcement | Default warn; enforce only when policy engine + tests say so |
| Agent latency | Timeouts + caching |
| Data duplication | Reuse **Entity**, avoid **BrainNode** duplicate |

---

## Open Questions

1. **Tenancy:** Is multi-project/org on the roadmap for this repo vs. a hosted “AXIOM Control” product fork?
2. **Auth:** OIDC vs API keys for agents first?
3. **Calibra:** When does Bayesian calibration land — should trust fields mirror Calibra exactly?
4. **Content storage:** Inline in `entity.data` vs blob store for large docs?
5. **Postgres:** Will production migrate from SQLite → Postgres (required for serious pgvector)?

---

## Recommended First Implementation Prompt

Use this **after Phase 0 sign-off**. It deliberately avoids ripping out architecture.

---

**Prompt (Phase 1 — Brain Foundation)**

> You are implementing Phase 1 of the Company Brain inside the **AXIOM-BRAIN** repo. Constraints:
> 
> 1. **Reuse** existing SQLAlchemy models **`Entity`, `Edge`, `Source`** — do **not** add `BrainNode` tables unless unavoidable; store brain-specific attributes under `entity.data` with documented keys (`trust_level`, `authority_rank`, `source_refs`, timestamps).
> 2. Add FastAPI routes in **a new module** (e.g. `src/axiom/api/brain.py`) and **include the router** from `studio/server.py` — avoid an unmaintainable giant `server.py`.
> 3. Routes (single-tenant, no auth yet): **`GET/PATCH /api/brain/nodes/{id}`, `POST /api/brain/nodes`, `GET /api/brain/edges`, `POST /api/brain/edges`** with Pydantic request/response models mirroring **`EntityDTO`/`EdgeDTO`** plus validated `relationship` for edge kinds.
> 4. On successful mutations, optionally insert a **`receipts`** row with `receipt_type="brain_entity_mutation"` (or **`brain_edge_mutation`**) containing before/after metadata, and **`EventBroadcaster.publish`** so **`/ws/brain`** clients refresh — follow patterns from ingest events.
> 5. Add **pytest** coverage: CRUD round-trip; invalid edge endpoints 404; relationship enum rejection.
> 6. **Do not** add pgvector, Redis, Next.js routes, or `PolicyProfileVersion`.
> 7. Run **`pytest`** and **`npm run build`** in `frontend`** if TypeScript/API types change.

---

**End of audit.**
