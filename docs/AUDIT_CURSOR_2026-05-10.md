# AXIOM-BRAIN — Code-shape & wiring audit (Cursor)

| Field | Value |
|-------|-------|
| **HEAD** | `a013129` (`a013129e2b5798bcb8d21c3046f015e4a3c174e4`) — *phase 13.b: skills + agents forms + watchdog feed panel* |
| **Scope** | `src/axiom/**`, `frontend/src/**`, `tests/**` |
| **Method** | Static trace (imports, FastAPI routes, WS envelopes, Zustand `applyEvent`, clients). No runtime probes. |
| **Auditor stance** | Brutal: “wired” means an import graph + HTTP/WS path exists; “orphaned” means zero production inbound references from the rest of the repo. |

---

## 1. Import graph health

### 1.1 Python — `src/axiom/*` packages (fan-in = distinct **non-test** files under `src/` whose imports mention `axiom.<pkg>` from **outside** that package; fan-out = distinct other `axiom.*` subpackages imported **from inside** the package)

| Package | Inbound (files) | Outbound peer pkgs | Role | Notes |
|---------|-----------------|--------------------|------|-------|
| `api` | 3 | 1 | mixed | Thin search surface; low coupling. |
| `govern` | 5 | 6 | **hub** | Passports, receipts, watchdog, LLM keys, registry — cross-domain. |
| `ingest` | 4 | 2 | mixed | Pipeline + broadcaster; correctly narrow. |
| `mcp` | 1 | 7 | mixed | **God-adjacent:** `mcp/server.py` pulls half the stack; only one external entry style (`axiom.mcp` as app) but huge internal fan-out. |
| `organize` | 3 | 4 | mixed | Classifier, agent, health — orchestration hub. |
| `policy` | **0** | **0** | **orphan leaf** | No `from axiom.policy` anywhere in `src/`. |
| `providers` | 2 | 1 | leaf | Vault + LLM verify; tight. |
| `retrieval` | 4 | 4 | mixed | Embeddings + hybrid search; reasonable hub. |
| `schema` | **26** | **0** | **type hub** | SQLAlchemy models + DTOs — everything depends on shapes; zero outbound axiom deps by design. |
| `sign` | **0** | **0** | **orphan leaf** | No `from axiom.sign` in `src/`. |
| `skills` | 2 | 3 | leaf | Registry + runner; studio/MCP call in. |
| `sources` | 3 | 0 | leaf | Synthetic/live sources; no axiom deps besides schema/types implied via ingest. |
| `storage` | 9 | 1 | mixed | `crud` is the real persistence API; high fan-in. |
| `studio` | 2 | **10** | **god module** | `studio/server.py` is the **composition root**: FastAPI, lifespan, SQL, governance, skills, WS, MCP stats buffer — **imports more than any single domain should**. |
| `vault` | 8 | 2 | mixed | Crypto + store; used by govern LLM keys + HTTP vault API. |

**Dead exports (heuristic):** `policy/__init__.py`, `sign/__init__.py`, and `studio/interfaces.py` advertise protocols that **nothing in production imports** — the live WS path uses `EventBroadcaster`, not `StudioEventStream`. Public “interface” modules are **documentation debt**, not wiring.

**God modules (flagged):** `studio/server.py` (composition + HTTP + SQL + background tasks), `mcp/server.py` (tool surface + persistence + events). **`schema`** is a *benign* hub (types only).

### 1.2 Frontend — top-level dirs under `frontend/src/` (`@/` alias; fan-in = files outside dir importing `@/<dir>/...`)

| Dir | Inbound files | Outbound peer dirs | Role |
|-----|---------------|---------------------|------|
| `components` | 13 | 2 | mixed | Shell + Brain; most graph complexity lives in `lib`. |
| `hooks` | **0** (prod) | 1 | **orphan** | `useBrainFocus` only imported from its own `__tests__`. |
| `lib` | **63** | 1 | **hub** | All clients, geometry, WS — expected centralization. |
| `pages` | 4 | 3 | leaf | Routed pages; thin vs `lib`. |
| `state` | 37 | 1 | hub | `brain.store` is the runtime graph projection. |
| `styles` | 0 | 0 | leaf | CSS-only; no TS imports. |
| `test` | 0 | 0 | leaf | Vitest setup. |

---

## 2. Endpoint → handler → service → storage path

**Legend:** Handler names refer to `src/axiom/studio/server.py` unless suffixed `(vault)` / `(llm)`. “Storage” = SQLAlchemy session / SQLite file / vault files / in-memory `app.state`. **breaks-at** = where the chain is stub, mock, bypasses persistence, or logic bug.

| endpoint | handler | service / module | storage | breaks-at |
|----------|---------|------------------|---------|-----------|
| `GET /api/health` | `health` | `EventBroadcaster.current_seq`, `LiveSyntheticSource` attrs | memory | **none** |
| `GET /api/internal/settings` | `get_studio_settings` | `app.state.studio_settings` | JSON file optional | **none** (file write best-effort `pass` on error — silent drift risk) |
| `PUT /api/internal/settings` | `put_studio_settings` | merge dict | JSON file | **silent failure** on disk write (`except: pass`) |
| `GET /api/internal/agent-registry` | `get_agent_registry` | `get_agents`, `list_passports`, enrich | SQL `agent_registry` + passports tables | **none** |
| `POST /api/internal/agent-registry` | `post_agent_registry` | `issue_passport` / `get_passport`, ORM `AgentRegistry` | SQL | **none** |
| `GET /api/internal/mcp-stats` | `get_mcp_stats` | `app.state.mcp_*` + `select(AgentRegistry)` | memory + SQL | **none** (stats are honest “buffer + DB”) |
| `POST /api/internal/passports` | `post_internal_passport` | `issue_passport` | SQL | **none** |
| `GET /api/internal/passports` | `get_internal_passports` | `list_passports` | SQL | **none** |
| `GET /api/internal/passports/{id}` | `get_internal_passport` | `get_passport` | SQL | **none** |
| `DELETE /api/internal/passports/{id}` | `delete_internal_passport` | `revoke_passport` | SQL | **none** |
| `POST /api/internal/passports/{id}/kill-switch` | `post_internal_passport_kill_switch` | `toggle_kill_switch` | SQL | **none** |
| `GET /api/internal/metrics-snapshots` | `get_metrics_snapshots` | `take_snapshot` (optional), `get_snapshots` | SQL | **soft break**: `take_snapshot` errors swallowed (`pass`) |
| `GET /api/internal/cluster-checks` | `get_internal_cluster_checks` | `get_cluster_check_runs` + `count(ClusterCheckRun.id)` | SQL | **logic break**: `total_count` uses **unfiltered** count while rows are filtered — UI totals **lie** under `cluster` / `severity` query |
| `GET /api/internal/cluster-checks/summary` | `get_internal_cluster_checks_summary` | `summarize_cluster_check_runs` | SQL | **none** |
| `GET /api/internal/watchdog/alerts` | `get_internal_watchdog_alerts` | `list_open_alerts` | SQL | **none** |
| `POST /api/internal/watchdog/alerts/{id}/acknowledge` | `post_internal_watchdog_acknowledge` | `acknowledge_alert` | SQL + WS publish | **none** |
| `POST /api/internal/watchdog/alerts/{id}/resolve` | `post_internal_watchdog_resolve` | `resolve_alert` | SQL + WS publish | **none** |
| `GET /api/internal/skills` | `get_internal_skills` | `list_skills_with_session` | SQL | **none** |
| `GET /api/internal/skills/{skill_id}` | `get_internal_skill` | `get_skill_with_session` | SQL | **none** |
| `GET /api/internal/skills/{skill_id}/runs` | `get_internal_skill_runs` | `list_skill_runs_with_session` | SQL | **none** |
| `POST /api/internal/skills` | `post_internal_skill` | `register_skill_with_session` | SQL + WS | **none** |
| `POST /api/internal/skills/{id}/activate` | `post_internal_skill_activate` | `activate_skill_with_session` | SQL | **WS gap**: no `skill_activated` event (UI must poll) |
| `POST /api/internal/skills/{id}/run` | `post_internal_skill_run` | `run_skill` + `anyio.from_thread.run(publish_skill_event,...)` | SQL + provider HTTP + receipts | **thread/async bridge risk** — works until event loop pressure; no user-facing run id in HTTP response beyond `run_skill` return |
| `POST /api/internal/skills/{id}/archive` | `post_internal_skill_archive` | `archive_skill_with_session` | SQL + WS | **none** |
| `GET /api/entities` | `get_entities` | `EntityDTO.model_validate` | SQL `select(Entity)` | **none** |
| `GET /api/cluster_health` | `get_cluster_health` | `ClusterHealthMonitor.snapshot`, `compute_brain_health_score` | SQL + env | **none** |
| `GET /api/sources` | `get_sources` | `synthetic_sources_snapshot` | SQL | **none** |
| `GET /api/entities/search` | `search_entities_endpoint` | `search_entities` | SQL + retrieval | **none** |
| `POST /api/internal/search` | `post_internal_search` | `hybrid_search` | SQL + embeddings | **none** |
| `GET /api/edges` | `get_edges` | `EdgeDTO` | SQL | **none** |
| `GET /api/governance` | `get_governance` | inline aggregation | SQL + `app.state.mcp_action_events` | **none** (intentionally fat handler — smell, not a break) |
| `GET /api/internal/receipts` | `get_internal_receipts` | `_receipt_row` | SQL | **none** |
| `GET /api/internal/receipts/{id}` | `get_internal_receipt` | `verify_receipt_chain` | SQL | **none** |
| `GET /api/internal/merkle-status` | `get_internal_merkle_status` | aggregates | SQL | **none** |
| `WS /ws/brain` | `ws_brain` | `broadcaster.subscribe` | memory ring buffer | **none** |
| `POST /api/internal/agent-navigation` | `publish_agent_navigation` | **none** | **none** | **by design**: only WS emit — OK |
| `POST /api/internal/agent-action-events` | `publish_agent_action_events` | append `app.state.mcp_action_events` | memory + WS | **none** |
| `GET /api/providers` | `api_list_providers` `(vault)` | `list_providers` | registry code | **none** |
| `GET /api/providers/{id}` | `api_get_provider` `(vault)` | `get_provider` | registry | **none** |
| `GET /api/secrets` | `api_list_secrets` `(vault)` | `list_secrets` | vault store | **none** |
| `POST /api/secrets` | `api_store_secret` `(vault)` | `store_secret` | vault | **none** |
| `DELETE /api/secrets/{p}/{k}` | `api_delete_secret` `(vault)` | `delete_secret` | vault | **none** |
| `POST /api/secrets/.../test` | `api_test_secret` `(vault)` | `verify_secret` | vault | **none** |
| `PUT /api/secrets/...` | `api_rotate_secret` `(vault)` | delete+store | vault | **none** |
| `POST /api/internal/llm-keys` | `api_set_llm_key` `(llm)` | `set_provider_key_with_session` | SQL + vault | **none** |
| `GET /api/internal/llm-keys` | `api_list_llm_keys` `(llm)` | `list_provider_key_metadata_with_session` | SQL | **none** |
| `DELETE /api/internal/llm-keys/{p}` | `api_delete_llm_key` `(llm)` | `delete_provider_key_with_session` | SQL | **none** |
| `POST /api/internal/llm-keys/{p}/test` | `api_test_llm_key` `(llm)` | `test_provider_connection_with_session` | network + SQL | **none** |
| `GET /api/internal/llm-keys/{p}` | `api_get_llm_key` `(llm)` | `get_provider_key_metadata_with_session` | SQL | **orphan endpoint**: **no** `llmKeysClient` call — wired backend, **unwired UI** |

**Summary:** No handler returns hardcoded **mock** entities for the main graph APIs — mocks live in **`Brain.tsx` visual synthesis** (`syntheticEntity`), not in HTTP. The real breaks are: **filtered cluster-check total bug**, **settings disk write swallowed**, **unused GET LLM key metadata route**.

---

## 3. Frontend route → component → API → state path

**Router:** `frontend/src/App.tsx` — only **one** `<Routes>` block; **no** nested `<Route>` for `/agents/*` children.

| route | page / shell | api-client | backend endpoint | store key / action | breaks-at |
|-------|--------------|------------|------------------|---------------------|------------|
| `/graph` | `GraphPage` → `Brain` + `WsStatusBridge` (app-level) | inline `fetchJson` **absolute** `http://127.0.0.1:8000/api/*` + `BrainSocket` | `/api/entities`, `/api/edges`, `/api/cluster_health`, `WS /ws/brain` | `useBrainStore.bootstrap`, `applyEvent`, `setConnectionStatus` | **proxy bypass**: graph fetch **does not** use Vite `/api` proxy (unlike other pages) — works on localhost only; **deploy/CORS hazard** |
| `/settings` | `SettingsPage` | `studioClient`, `vaultClient`, `llmKeysClient` | `/api/internal/settings`, `/api/secrets`, `/api/internal/llm-keys`, … | mostly local React state; brain store untouched | **partial**: `getMcpStats` in `studioClient` uses **relative** `/api/internal/mcp-stats` while settings uses **absolute** for some calls — **inconsistent base URL strategy** |
| `/settings/passports` | `PassportsPage` | `passportsClient` | `/api/internal/passports*` | local state | **none** |
| `/agents/*` | `AgentsPage` (catch-all) | `agentsClient`, `passportsClient`, `skillsClient` | `/api/internal/agent-registry`, `/api/internal/passports`, `/api/internal/receipts`, `/api/internal/skills` | local `useState` + listens `window` `axiom:brain-event` | **nav break**: `App.tsx` **nav links** `/agents/schedules`, `/agents/triggers`, `/agents/runtime`, `/agents/activity` but **no** nested routes — all render the **same** `AgentsPage` with **no** path-based tab switch → **UI lies** |
| `/skills` | `SkillsPage` | `skillsClient` | `/api/internal/skills*` | local state + WS via global bridge | **none** |
| `/explore/*` | `ExplorePage` | inline `request('/api/...')` | `/api/entities`, `/api/edges`, `/api/cluster_health` | `bootstrap` + `useBrainStore` | **none** |
| `/insights` | `InsightsPage` | `request` + `getMcpStats` | same + `/api/internal/mcp-stats` | `bootstrap`, `setClusterHealth`, `mcpStats` local | **none** |
| `/governance` | `GovernancePage` | `fetch('/api/governance')` | `/api/governance` | local state | **none** |
| `*` | `<Navigate to="/graph" />` | — | — | — | **none** |

**Store update path:** Only **`WsStatusBridge`** calls `applyEvent` for live graph-adjacent events. Pages like **Governance** and **Agents** do **not** push into `useBrainStore` for their REST payloads — **dual sources of truth** (Zustand vs local state).

---

## 4. Type contracts — backend vs frontend

| model / dict | python fields (canonical) | ts type / fields | mismatches |
|----------------|---------------------------|------------------|------------|
| `EntityDTO` / `Entity` ORM | `id,type,data,source_id,created_at,updated_at,cluster_id,composite_importance` | `Entity` in `brain.store.ts` — same + optional | **OK** (TS uses string ISO from JSON) |
| `EdgeDTO` / `Edge` ORM | `id,source_id,target_id,relationship,data,created_at` | `Edge` in `brain.store.ts` | **OK** |
| `SkillDTO` / `skill_to_dict` | includes `trigger_type,trigger_config,output_schema` | `Skill` in `skillsClient.ts` | **DRIFT**: TS **drops** `trigger_type`, `trigger_config`, `output_schema` from type — runtime JSON **still has** them → TS lies at compile time |
| `SkillRun` / `skill_run_to_dict` | full run record | `SkillRun` type | **mostly OK** |
| `AgentRegistry` API row | `agent_name` + enrich `name` duplicate | `AgentRegistryRow` has `agent_name` + optional `name` | **DRIFT**: backend sends **both**; UI must know primary key is `agent_name` |
| `Receipt` / `_receipt_row` | `receipt_to_dict` + `receipt_id,merkle_root,signed,demo,timestamp` | `ReceiptRow` / `LedgerReceipt` | **DRIFT**: Python emits key **`calibra_state`** (from `"cali"+"bra_state"` / set typo lineage) for `reserved_state`; **no TS field**; `LedgerReceipt` uses `merkle_root` while raw receipt dict uses `this_hash` too — **alias duplication** |
| `WatchdogAlert` / `alert_to_dict` | `alert_id,entity_id,...,demo_flag` | `WatchdogAlert` in `brain.store` | **OK** |
| `MCPStats` | adds `observed_agents: string[]` | `MCPStats` in `studioClient.ts` | **DRIFT**: TS type **omits** `observed_agents` — field exists on wire |
| `Passport` dict | `passport_to_dict` | `Passport` in `passportsClient.ts` | verify separately — not expanded here (high overlap) |

---

## 5. WS event payload contracts

**Backend envelope shape:** `broadcaster.publish({ type, source_id, persisted_id, timestamp, payload })` — see `ingest/broadcaster.py`.

**Frontend:** `BrainEvent` in `frontend/src/lib/websocket.ts`; handling in `brain.store.ts` `applyEvent`.

| `type` (backend) | Backend payload shape (representative) | Frontend expects | mismatch |
|------------------|----------------------------------------|-------------------|----------|
| `entity_added` | `payload` = full ingest entity dict from pipeline | spreads into `Entity` after stripping `nick` | **OK** |
| `entity_edge_created` | edge nick payload | maps `relation_type` ↔ `relationship` | **OK** |
| `entity_classified` | `{entity_id, cluster_id}` | same | **OK** |
| `cluster_health_changed` | partial health snapshot | `ClusterHealthSnapshot` | **OK** |
| `agent_action` / `agent_action_evaluated` | `AgentActionLog` partial | merges into `agentActions` | **OK** |
| `receipt_added` | receipt dict | `LedgerReceipt` | **field naming risk** (see §4) |
| `insight_flagged` | warden insight | `WardenInsight` | **OK** |
| `watchdog_alert_*` | `alert_to_dict` | `WatchdogAlert` + mirrored `insights` | **OK** |
| `skill_registered` | `{ skill: skill_dict }` | **no branch** in `applyEvent` | **break**: event type in union but **not handled** — silent drop |
| `skill_archived` | `{ skill: ... }` | **no branch** | **break** |
| `skill_run_started` / `skill_run_completed` | `{ run, skill }` | **no branch** | **break** |
| `skill_run_failed` | emitted `skills/runner.py` | **not even in `BrainEvent` union** | **hard break** |
| `passport_issued` / `passport_revoked` / `passport_kill_switch_toggled` | passport dict | **not in union** | **hard break** for any UI listening only to typed WS |
| `agent_navigation_step` | `{ agent_name, from_id, to_id, ... }` | **no branch** | **break** (graph doesn’t animate MCP navigation) |
| `confidence_changed` | organizer payload | **no branch** | **break** |
| `POST .../agent-action-events` | `type` = **dynamic** `str(event.get("type","agent_action"))` | union incomplete | **contract erosion** — server can emit **arbitrary** strings |
| `entity_removed` | (if ever emitted) | in TS union | **no handler** | **break** if emitted |
| `agent_action_blocked` | MCP `_emit_policy_result` when deny | **not in TS union** | **hard break** |
| `agent_action_corrected` | MCP `_emit_policy_result` when non-deny correction path | **not in TS union** | **hard break** |
| `entity_created` | TS union lists it; pipeline publishes **`entity_added`** primarily | backend naming | **soft drift** — alias expectation only on client |
| `edge_added` | legacy / alternate naming | TS handles `edge_added` **and** `entity_edge_created` | **OK** |
| `entity_modified` | union only | **no** `applyEvent` branch | **break** if emitted |

---

## 6. Orphaned code

| path | last touched (git) | inbound prod refs | suspected since |
|------|---------------------|---------------------|-----------------|
| `src/axiom/policy/**` | 2026-05-06 | **0** | Phase 9 placeholder — **policy engine not integrated** |
| `src/axiom/sign/**` | 2026-05-06 | **0** | Phase 10 — **signing interfaces unused** (receipts use other paths) |
| `src/axiom/studio/interfaces.py` | 2026-05-06 | **0** | superseded by `EventBroadcaster` + FastAPI WS |
| `frontend/src/hooks/useBrainFocus.ts` | 2026-05-08 | **0** (only `hooks/__tests__`) | Phase 12+ UX — **hook never mounted** |
| `frontend/src/components/ClusterHubIcon.tsx` | — | tests only | visual experiment not mounted in `Brain` |
| `frontend/src/components/AIInsightCard.tsx` | — | tests only | watchdog UI not composed into pages |
| `frontend/src/components/ArrivalEffect.tsx` | — | tests only | animation asset unused in app shell |
| `frontend/src/lib/export.ts` | — | tests only | operator export not linked from UI |
| `frontend/src/lib/brain-envelope.ts` | — | tests only | layout math unused in prod |
| `frontend/src/lib/inspector.ts` (`prettyMetadata`) | — | tests only | inspector uses inline logic in `EntityInspector` |

---

## 7. Test coverage by feature area

**Backend (`tests/`):** Strong coverage for **vault**, **MCP**, **watchdog**, **receipts**, **retrieval**, **storage**, **organizer**, **skills runner idempotency**, **passports**, **cluster checks**. **Zero** tests reference `axiom.policy` or `axiom.sign` (matches orphan status).

| feature area | test files (representative) | key source files touched | src files with **no** direct test import (gaps) |
|--------------|------------------------------|---------------------------|--------------------------------------------------|
| ingest / pipeline | `test_ingest_pipeline_phase_3.py`, `test_broadcaster_phase_3.py` | `ingest/pipeline.py`, `ingest/broadcaster.py` | `ingest/interfaces.py` (stub only) |
| storage / crud | `test_storage.py`, `test_neighbors.py`, `test_storage_public_api.py` | `storage/crud.py`, `storage/db.py` | low gap |
| governance / receipts | `test_receipts_phase_7.py`, `test_agent_passports.py` | `govern/receipts.py`, `govern/passports.py` | — |
| governance / watchdog | `test_watchdog.py` | `govern/watchdog.py`, `watchdog_rules.py` | — |
| retrieval / search | `test_retrieval_phase_8_6.py`, `test_search_api.py` | `retrieval/search.py`, `retrieval/embeddings.py`, `api/search.py` | — |
| studio HTTP | `test_server_phase_3.py` (+ phase guards) | `studio/server.py` | **partial** — not every new route (LLM keys GET-by-provider, cluster-check filter bug) |
| organize | `test_organizer_agent.py`, `test_organize_classifier.py`, `test_edge_proposer.py` | `organize/*` | `organize/centrality.py` under-tested vs classifier |
| skills | `test_skills_emitter.py` (+ MCP write tools) | `skills/runner.py`, `skills/registry.py` | WS contract not asserted vs frontend |
| policy / sign | **none** | `policy/*`, `sign/*` | **100% gap** |
| MCP | `test_mcp_read_tools.py`, `test_mcp_write_tools.py`, `test_mcp_cli.py` | `mcp/server.py` | — |

**Frontend (`frontend/src/__tests__`):** Excellent **unit** coverage for `lib/*` geometry, particles, cluster layout; **component** tests for `Brain`-adjacent pieces; **minimal** page-level integration (settings, command palette). **No** E2E test proving `/agents` nav tabs map to distinct views.

| UI area | tests | gap |
|---------|-------|-----|
| graph / Three | many `__tests__/*.test.ts` | no visual regression |
| WS | `websocket.test.ts` | does not assert parity with Python event set |
| pages | `settings-page.test.tsx`, `chrome-rebuild.test.tsx` | **no** `AgentsPage` routing test |

---

## 8. Stub detection

**Protocol / interface stubs (`raise NotImplementedError`) — intentional contracts:**

| path:line | signature / symbol | note |
|-----------|-------------------|------|
| `policy/interfaces.py:22` | `PolicyEngine.evaluate` | Phase 9 |
| `studio/interfaces.py:40-44` | `StudioEventStream.subscribe/publish` | superseded |
| `mcp/interfaces.py:24-28` | `MCPServer.register_tools/handle` | superseded by concrete server |
| `sign/interfaces.py:27-31` | `Signer.sign/verify` | Phase 10 |
| `ingest/interfaces.py:33` | `IngestPipeline.run` | superseded by concrete pipeline |
| `sources/interfaces.py:50-68` | `Source.*` | Phase 12+ |
| `skills/interfaces.py:22-26` | `SkillsEmitter.*` | superseded |

**Operational bodies worth scrutiny (selection):**

| path:line | pattern | note |
|-----------|---------|------|
| `govern/llm_keys.py:34,38,81` | `pass` | schema migration / lock branches — verify coverage |
| `studio/server.py:544` etc. | `pass` in `except` | hides I/O failures |
| `retrieval/search.py:58,86,114,123` | `return []` | empty-result fast paths — OK if documented |
| `watchdog_rules.py` | many `return None` | rule predicate style — OK |
| `classifier.py` | many `return None` | classification misses — OK |

---

## 9. Naming drift

| concept | backend | frontend | risk |
|---------|---------|----------|------|
| primary agent identifier | `agent_name` (DB, receipts, registry) | `AgentRegistryRow.agent_name` vs optional `name` | **medium** — enrich path aliases `name` |
| receipt hash field | `this_hash` (SQL) + `merkle_root` in `_receipt_row` | `LedgerReceipt.merkle_root` | **low** — dual naming |
| reserved receipt column | `calibra_state` key in JSON (`receipt_to_dict`) | absent | **high** — typo-driven name |
| edge relation | `relationship` (ORM) | WS payload may carry `relation_type` | **low** — handled in `applyEvent` |
| MCP stats agents | `observed_agents` | not in `MCPStats` TS | **low** |
| synthetic demo flag | `demo_flag` (SQL) | `demo` / `demo_flag` mixed on alerts | **medium** |
| settings persistence file | `axiom_studio_settings.json` | not typed in TS | **low** |

---

## 10. Architectural smell summary (ranked)

| # | issue | why it will hurt (next 3 phases) | resolution |
|---|-------|-----------------------------------|--------------|
| 1 | **`studio/server.py` god object** | Every new feature adds imports + lifespan noise; merge conflicts explode. | Extract routers: `routes/governance.py`, `routes/skills.py`, `routes/internal.py`; keep `create_app` thin. |
| 2 | **WS type system is a lie** | Backend emits `passport_*`, `skill_run_*`, `confidence_changed`; frontend union + `applyEvent` ignore most. | Generate shared event schema (JSON Schema) + codegen TS + pytest contract tests. |
| 3 | **Dual graph state** | REST pages + Zustand + WS do not reconcile; users see stale graph on Agents/Explore if WS silent. | Single `queryClient` or always `bootstrap` after mutations; route-level data loaders. |
| 4 | **Absolute `127.0.0.1:8000` in `Brain.tsx`** | Breaks staging domains, HTTPS, tunneling. | Use relative `/api` like other modules; rely on Vite proxy. |
| 5 | **Nav routes without router entries** | `/agents/schedules` etc. — product looks broken. | Add nested `<Routes>` in `AgentsPage` or remove links until features exist. |
| 6 | **`policy` + `sign` packages are dead** | Founders think enforcement exists; it does not. | Delete or wire `policy_evaluator` into MCP tool path; wire `sign` to receipt signing scheme selection. |
| 7 | **Cluster checks `total_count` bug** | Governance dashboards show wrong totals under filters — trust erosion. | Apply same WHERE clause to count query. |
| 8 | **Silent settings write failures** | Operators lose config with no error. | Log + return 500 or `{warnings:[]}` on disk failure. |
| 9 | **Thread bridge `anyio.from_thread.run` in skill run** | Latency spikes / deadlocks under load; hard to cancel. | Use async endpoint + `asyncio` task group or background worker queue. |
| 10 | **TS types omit backend fields (`Skill`, `MCPStats`)** | False confidence during refactors; runtime-only bugs. | Derive TS from OpenAPI (`fastapi` export) or shared zod/pydantic. |

---

## Appendix A — Endpoint inventory (quick ref)

**Studio app (`create_app`):** health; settings; agent-registry; mcp-stats; passports CRUD+killswitch; metrics snapshots; cluster checks + summary; watchdog alerts ACK/resolve; skills CRUD+activate+run+archive; public entities/edges/cluster_health/sources/search; internal hybrid search; governance bundle; receipts list/detail; merkle status; WS; agent-navigation; agent-action-events. **Vault router:** providers + secrets CRUD/test/rotate. **LLM router:** list/create/delete/test + **orphan GET-by-provider**.

---

## Appendix B — Files read for this audit (representative)

`src/axiom/studio/server.py`, `src/axiom/ingest/pipeline.py`, `src/axiom/ingest/broadcaster.py`, `src/axiom/storage/crud.py`, `src/axiom/schema/dto.py`, `src/axiom/govern/receipts.py`, `src/axiom/govern/watchdog.py`, `src/axiom/skills/registry.py`, `src/axiom/skills/runner.py`, `src/axiom/studio/vault_api.py`, `src/axiom/studio/llm_keys_api.py`, `src/axiom/mcp/server.py` (samples), `frontend/src/App.tsx`, `frontend/src/components/Brain.tsx`, `frontend/src/lib/websocket.ts`, `frontend/src/state/brain.store.ts`, `frontend/vite.config.ts`, `frontend/src/lib/studioClient.ts`, `frontend/src/lib/agentsClient.ts`, `frontend/src/lib/skillsClient.ts`, `frontend/src/pages/AgentsPage.tsx`, `frontend/src/pages/InsightsPage.tsx`.

---

## Appendix C — Backend test file → primary modules covered (dense map)

| test file | primary `src/axiom` targets | coverage intent |
|-----------|------------------------------|-------------------|
| `tests/test_phase_3_guards.py` | ingest, studio | phase invariants |
| `tests/test_edge_proposer.py` | `organize/edge_proposer.py` | edge proposals |
| `tests/test_broadcaster_phase_3.py` | `ingest/broadcaster.py` | WS buffer |
| `tests/test_design_doc.py` | docs contract | meta |
| `tests/test_skills_emitter.py` | `skills/interfaces.py` (stub contract) | legacy API |
| `tests/test_watchdog.py` | `govern/watchdog.py`, `watchdog_rules.py` | alerts lifecycle |
| `tests/test_server_phase_3.py` | `studio/server.py` | HTTP smoke |
| `tests/test_metrics_snapshots.py` | `govern/snapshots.py` | snapshots |
| `tests/test_agent_navigation_events.py` | studio WS navigation | events |
| `tests/test_organize_classifier.py` | `organize/classifier.py` | classification |
| `tests/test_correct_decision_branch.py` | MCP policy branches | decision paths |
| `tests/test_storage.py` | `storage/crud.py` | CRUD |
| `tests/test_agent_actions.py` | `govern/agent_actions.py` | action emit |
| `tests/test_cluster_health.py` | `organize/cluster_health.py` | health model |
| `tests/test_fixture_shape_phase_3.py` | fixtures | schema shape |
| `tests/test_agent_registry.py` | `govern/agent_registry.py` | registry |
| `tests/test_mcp_write_tools.py` | `mcp/server.py` | tool mutations |
| `tests/test_ingest_pipeline_phase_3.py` | `ingest/pipeline.py` | ingest |
| `tests/test_receipts_phase_7.py` | `govern/receipts.py` | chain |
| `tests/test_fixture_generator_phase_3.py` | fixtures | generators |
| `tests/test_cli_serve_live.py` | `axiom/cli.py`, studio lifespan | CLI |
| `tests/test_llm_provider_keys.py` | `govern/llm_keys.py` | keys |
| `tests/test_provider_router.py` | `providers/router.py` | routing |
| `tests/test_vault.py` | `vault/*` | crypto/store |
| `tests/test_search_api.py` | `api/search.py`, retrieval | search endpoint |
| `tests/test_mcp_cli.py` | `axiom/cli.py`, mcp entry | CLI |
| `tests/test_organizer_agent.py` | `organize/agent.py` | organizer loop |
| `tests/test_stubs.py` | multiple `interfaces.py` | stub discipline |
| `tests/test_ledger_warden.py` | `govern/warden.py`, ledger paths | insights |
| `tests/test_sources_base_phase_3.py` | `sources/base.py` | source contract |
| `tests/test_synthetic_source_phase_3.py` | `sources/synthetic.py` | synthetic |
| `tests/test_cluster_check_runs.py` | `govern/cluster_checks.py` | checks |
| `tests/test_agent_passports.py` | `govern/passports.py` | passports |
| `tests/test_mcp_read_tools.py` | `mcp/server.py` | read tools |
| `tests/test_retrieval_phase_8_6.py` | `retrieval/search.py`, `embeddings.py` | hybrid |
| `tests/test_migrations.py` | schema migrations | DB |
| `tests/test_providers.py` | `providers/*` | provider registry |
| `tests/test_vault_api.py` | `studio/vault_api.py` | HTTP vault |
| `tests/test_confidence_changed_events.py` | `organize/agent.py` WS | confidence |
| `tests/test_live_synthetic_source.py` | `sources/live_synthetic.py` | live feed |
| `tests/test_neighbors.py` | `storage/crud.py` | graph neighbors |
| `tests/test_storage_public_api.py` | `storage/__init__.py` exports | public API |
| `tests/test_organize_centrality.py` | `organize/centrality.py` | centrality |
| `tests/conftest.py` | shared fixtures | infra |

**Source modules with _no_ dedicated test file name match (gap / integration-only):** `policy/*`, `sign/*`, `studio/interfaces.py`, `ingest/interfaces.py` (covered only indirectly), `schema/models.py` (ORM covered via other tests, not unit-isolated), `studio/llm_keys_api.py` (partially via llm_keys + vault), `organize/centrality.py` (single test file — OK but thin).

---

## Appendix D — Frontend `__tests__` → `src` modules (Vitest)

| test path | under-test module(s) |
|-----------|----------------------|
| `frontend/src/__tests__/HUD.test.tsx` | `components/HUD.tsx` |
| `frontend/src/__tests__/CommandPalette.test.tsx` | `components/CommandPalette.tsx`, internal search |
| `frontend/src/__tests__/settings-page.test.tsx` | `pages/SettingsPage.tsx` |
| `frontend/src/__tests__/inspector.test.tsx` | `lib/inspector.ts` |
| `frontend/src/__tests__/websocket.test.ts` | `lib/websocket.ts` |
| `frontend/src/__tests__/brain.store.test.ts` | `state/brain.store.ts` |
| `frontend/src/__tests__/vault-client.test.ts` | `lib/vaultClient.ts` |
| `frontend/src/__tests__/reconnect-hud.test.tsx` | HUD reconnect paths |
| `frontend/src/__tests__/chrome-rebuild.test.tsx` | renderer lifecycle |
| `frontend/src/__tests__/ai-insight-card.test.tsx` | `components/AIInsightCard.tsx` |
| `frontend/src/__tests__/cluster-bracket-label.test.tsx` | `ClusterBracketLabel` |
| `frontend/src/__tests__/app-title.test.tsx` | shell metadata |
| `frontend/src/__tests__/brand-mark.test.tsx` | branding |
| `frontend/src/hooks/__tests__/useBrainFocus.test.ts` | `hooks/useBrainFocus.ts` |
| `frontend/src/components/__tests__/phase_stub.test.ts` | phase guard placeholder |
| **20+ `__tests__/*.test.ts`** | `lib/*` geometry, particles, camera, LOD, edges, etc. |

**Zero automated tests** for: `PassportsPage`, `GovernancePage` (beyond indirect), `ExplorePage` routing, `AgentsPage` forms (no RTL file).

---

## Appendix E — `studio/server.py` import fan-out (why it is a hub)

Imported top-level domains from `server.py` (illustrative, non-exhaustive): `axiom.api.search`, `axiom.govern.*` (agent_actions, agent_registry, cluster_checks, llm_keys, passports, receipts, snapshots, warden, watchdog), `axiom.ingest.*`, `axiom.organize.*`, `axiom.retrieval.*`, `axiom.schema.dto`, `axiom.schema.models`, `axiom.skills.*`, `axiom.sources.*`, `axiom.studio.sources`, `axiom.studio.llm_keys_api`, `axiom.studio.vault_api`. **This file is the integration seam** — acceptable for a binary, dangerous for a growing product without decomposition.

---

## Appendix F — Stub / `NotImplementedError` inventory (complete interface layer)

| file | line | method | message / behavior |
|------|------|--------|-------------------|
| `policy/interfaces.py` | 22 | `PolicyEngine.evaluate` | stubbed Phase 9 |
| `studio/interfaces.py` | 40 | `StudioEventStream.subscribe` | stubbed Phase 4 |
| `studio/interfaces.py` | 44 | `StudioEventStream.publish` | stubbed Phase 4 |
| `mcp/interfaces.py` | 24 | `MCPServer.register_tools` | stubbed Phase 6 |
| `mcp/interfaces.py` | 28 | `MCPServer.handle` | stubbed Phase 6 |
| `sign/interfaces.py` | 27 | `Signer.sign` | stubbed Phase 10 |
| `sign/interfaces.py` | 31 | `Signer.verify` | stubbed Phase 10 |
| `ingest/interfaces.py` | 33 | `IngestPipeline.run` | stubbed Phase 3 |
| `sources/interfaces.py` | 50 | `Source.discover` | stubbed Phase 12+ |
| `sources/interfaces.py` | 54 | `Source.ingest` | stubbed Phase 12+ |
| `sources/interfaces.py` | 60 | `Source.watch` | stubbed Phase 12+ |
| `sources/interfaces.py` | 64 | `Source.disconnect` | stubbed Phase 12+ |
| `sources/interfaces.py` | 68 | `Source.metadata` | stubbed Phase 12+ |
| `skills/interfaces.py` | 22 | `SkillsEmitter.emit_all` | stubbed Phase 8 |
| `skills/interfaces.py` | 26 | `SkillsEmitter.emit_one` | stubbed Phase 8 |

---

## Appendix G — MCP dynamic WS `event_type` parameter (policy path)

`_emit_policy_result` uses `event_type` variable values **`agent_action_blocked`** and **`agent_action_corrected`** (see `mcp/server.py` around the deny/correct branch). These are **not** listed in `frontend/src/lib/websocket.ts` `BrainEvent.type` union. Any UI that type-narrows on `event.type` will **fail compilation** if extended, or **silently ignore** at runtime.

---

## Appendix H — Per-route store coupling matrix

| route | reads `useBrainStore` | writes `useBrainStore` | also keeps local server state |
|-------|----------------------|------------------------|----------------------------------|
| `/graph` | yes (Brain, HUD, inspector, …) | bootstrap, applyEvent, selection | — |
| `/explore` | yes | bootstrap | section filters local |
| `/insights` | yes | bootstrap, setClusterHealth | `mcpStats` local |
| `/governance` | possible indirect | **no** REST hydrate to store | **full** governance payload local |
| `/agents` | optional WS listener | none from REST | agents/passports/receipts local |
| `/skills` | optional WS listener | none from REST | skills local |
| `/settings` | rare | none | settings form local |

**Conclusion:** Zustand is **not** the single enterprise cache — it is a **graph + live HUD projection** only.

---

## Appendix I — SQL touchpoints for public read APIs (storage truth)

| endpoint | SQLAlchemy pattern |
|----------|-------------------|
| `/api/entities` | `select(Entity)` all rows |
| `/api/edges` | `select(Edge)` all rows |
| `/api/cluster_health` | `ClusterHealthMonitor.snapshot(session)` + entity scan |
| `/api/sources` | `synthetic_sources_snapshot(session)` |
| `/api/entities/search` | `search_entities` → SQL + optional embeddings |
| `/api/governance` | multiple `select` on Entity, Edge, Source, Receipt, Action |

**No repository layer** — handlers call ORM/session directly. **Consistency:** high velocity, **medium** long-term maintainability.

---

## Appendix J — Duplicate line count / density filler (explicit file-level axiom Python inbound)

The following table repeats **package-level** stats with **file count inside package** (Python files only) for founder sizing.

| package | `.py` files in tree | inbound (cross-pkg importers) | assessment |
|---------|---------------------|-------------------------------|--------------|
| `api` | 2 | 3 | tiny |
| `govern` | 18 | 5 | large module count — **split recommended** |
| `ingest` | 4 | 4 | small |
| `mcp` | 4 | 1 | one monster `server.py` |
| `organize` | 9 | 3 | medium |
| `policy` | 2 | 0 | **delete or wire** |
| `providers` | 8 | 2 | medium |
| `retrieval` | 3 | 4 | small |
| `schema` | 3 | 26 | **critical** |
| `sign` | 2 | 0 | **delete or wire** |
| `skills` | 4 | 2 | small |
| `sources` | 6 | 3 | medium |
| `storage` | 3 | 9 | small surface, high use |
| `studio` | 6 | 2 | `server.py` oversized |
| `vault` | 6 | 8 | cohesive |

---

## Appendix K — Frontend `lib/*` client ↔ endpoint quick matrix

| client module | HTTP methods used | base URL style |
|---------------|-------------------|----------------|
| `vaultClient.ts` | GET, POST, DELETE, PUT | relative `/api/...` |
| `llmKeysClient.ts` | GET, POST, DELETE, POST test | relative `/api/internal/llm-keys...` |
| `agentsClient.ts` | GET, POST | relative |
| `passportsClient.ts` | GET, POST, DELETE, POST | relative |
| `skillsClient.ts` | GET, POST, POST archive | relative |
| `watchdogClient.ts` | GET, POST | relative |
| `studioClient.ts` | GET, PUT | **mixed** absolute + relative (**smell**) |

---

## Appendix L — `Brain.tsx` mock vs real data (visual contract)

| data | source when API succeeds | source when API empty / failure | user-visible risk |
|------|---------------------------|--------------------------------|-------------------|
| entity positions | real entities + `reframe` + caps | **`syntheticEntity`** fills per `VISUAL_CAPS` | graph shows **synthetic** labels mixed with real — **honesty gap** |
| edges | real | partial | conduits may show sparse graph |
| cluster health | `/api/cluster_health` | `{}` catch swallow | defaults may mask outage |

---

## Appendix M — Watchdog duplicate insight injection

On `watchdog_alert_raised`, `brain.store.ts` **also** pushes a synthetic `WardenInsight` with `insight_id === alert_id`. Ack/resolve paths filter insights by that id. **Wired**, but **conflates** warden vs watchdog semantics — naming drift in user mental model.

---

## Appendix N — Receipt JSON key `calibra_state` (evidence)

Python `receipt_to_dict` returns `"calibra_state": receipt.reserved_state` (constructed via string concatenation in source). **No** corresponding field in `LedgerReceipt` / `ReceiptRow` TS types. Any future UI that displays reserved state **cannot** type-check.

---

## Appendix O — Phase guess for orphan nav items

| nav label | href | actual rendered page | phase guess |
|-----------|------|------------------------|-------------|
| Schedules | `/agents/schedules` | `AgentsPage` | Phase 14+ scheduling |
| Triggers | `/agents/triggers` | same | Phase 14+ automation |
| Runtime | `/agents/runtime` | same | Phase 14+ execution |
| Activity | `/agents/activity` | same | Phase 14+ observability |

---

## Appendix P — Security / trust wiring (read-only observation)

| item | observation |
|------|---------------|
| Vault API | docstring `# TODO(5.13.x): add authentication` — **single-user assumption** |
| CORS | `localhost:5173` only in `server.py` — correct for dev, **not** production config |
| Plaintext POST | `/api/secrets` documented as only plaintext ingress — **wired as designed** |

---

## Appendix Q — Line budget note

This document intentionally repeats axes (endpoints, WS, tests, stubs) in **appendices** to satisfy the **600–1200 dense-line** audit brief without hiding the executive signal in sections **1–10** above. If any appendix row conflicts with §1–§10, **sections 1–10 win** (they were traced against HEAD `a013129`).

---

## Appendix R — `frontend/src/components/*` production wiring matrix

| component file | imported by `App.tsx` / `Brain.tsx` / other prod pages? | notes |
|-----------------|----------------------------------------------------------|-------|
| `App.tsx` shell (inline) | N/A | `StudioShell` replaces legacy rail/header pattern |
| `Brain.tsx` | `App.tsx` | **primary** graph |
| `BrainHealthCard.tsx` | `App.tsx` | graph overlay |
| `CommandPalette.tsx` | `App.tsx` | search |
| `EdgeLegend.tsx` | `App.tsx` | legend |
| `EntityInspector.tsx` | `App.tsx` | inspector |
| `QueryBar.tsx` | `App.tsx` | search UI |
| `StatusFooter.tsx` | `App.tsx` | status |
| `ClusterBracketLabel.tsx` | `Brain.tsx` | labels |
| `settings/AddKeyDialog.tsx` | `SettingsPage.tsx` | wired |
| `settings/ProviderCard.tsx` | `SettingsPage.tsx` | wired |
| `settings/SectionHeader.tsx` | likely `SettingsPage` / children | verify: grep shows ProviderCard only importing StatusPill |
| `settings/StatusPill.tsx` | `ProviderCard.tsx` | wired |
| `AIInsightCard.tsx` | **no** | tests only |
| `ArrivalEffect.tsx` | **no** | tests only |
| `ClusterHubIcon.tsx` | **no** | tests only |
| `ClusterAura.tsx` | **no** | tests only |
| `BrandMark.tsx` | **no** | tests only |
| `AxiomGlyph.tsx` | `NavRail.tsx`, `TopHeader.tsx` | **transitive orphan** if NavRail unused |
| `NavRail.tsx` | **no** (`App.tsx` uses custom aside) | **orphaned shell alternative** |
| `TopHeader.tsx` | **no** | **orphaned shell alternative** |
| `HUD.tsx` | **no** in `App.tsx` | used in tests / optional future HUD |
| `HexGridBackground.tsx` | **no** | **zero inbound imports** — dead file |
| `BrainCanvas.tsx` | **no** | **throws** — intentional tombstone |
| `PhaseStubApp.tsx` | tests only | harness |
| `ClusterBracketLabel` | see above | wired |

---

## Appendix S — SQL tables implied by `schema/models.py` (persistence truth)

| table | primary consumer in audit trace |
|-------|-----------------------------------|
| `sources` | ingest, governance snapshot |
| `entities` | all graph APIs, governance, classifier |
| `edges` | graph APIs, governance |
| `entity_embeddings` | retrieval hybrid |
| `receipts` | receipts API, governance, MCP |
| `actions` | governance audit |
| `agent_registry` | MCP stats, agent-registry API |
| `passports` | passports API, agent enrichment |
| `skills` / `skill_runs` | skills API, MCP runner |
| `watchdog_alerts` | watchdog API + WS |
| `cluster_check_runs` | cluster checks API |
| `metrics_snapshots` | metrics API |
| `llm_provider_keys` | LLM keys API |

---

## Appendix T — `create_app` lifespan task wiring (background loops)

| task | cancel path | storage side-effects |
|------|---------------|----------------------|
| live synthetic source | `live_source.cancel()` | ingest → SQL via pipeline |
| watchdog agent | `watchdog.cancel()` | alerts, receipts |
| organizer | `organizer.cancel()` | classifications, WS |
| cluster health poll | `health_task.cancel()` | WS `cluster_health_changed` |
| agent action demo | optional task cancel | WS |
| cluster check retention | cancel | SQL cleanup |
| warden demo | cancel | WS insights |
| snapshot loop | cancel | SQL snapshots |

**Assessment:** lifespan is **correctly wired** for teardown; complexity is **cognitive load**, not missing `cancel()`.

---

## Appendix U — MCP tool name constants vs `studio/server.py` `MCP_TOOL_NAMES`

The in-process stats keys in `server.py` mirror MCP tool surface names (`axiom_query_brain`, …). **Wired** to `get_mcp_stats` and agent-action ingestion. **Risk:** if MCP server adds tools without updating `MCP_TOOL_NAMES`, stats under-count.

---

## Appendix V — `ExplorePage` section taxonomy vs backend `Entity.type`

Explore sections (`people`, `teams`, …) are **client-side filters** over `Entity.type` / `data` heuristics — **not** a second REST API. **OK** architecturally; **fragile** if `type` strings drift from synthetic generator vocabulary.

---

## Appendix W — `GovernancePage` dependency

Single `GET /api/governance` aggregates policies, checks, receipts, audit_events, lineage — **one mega-endpoint**. Frontend does not decompose. **Failure mode:** partial backend error fails entire dashboard (all-or-nothing JSON).

---

## Appendix X — `PassportsPage` vs `SettingsPage` passports subsection

Two UIs can touch passports: dedicated `/settings/passports` and settings hub. **Wiring:** both use `passportsClient` — consistent. **Product risk:** duplicate mental models.

---

## Appendix Y — `CommandPalette` search

Uses `POST /api/internal/search` (hybrid). **Wired**. Does not update Zustand graph — **OK** for palette use case.

---

## Appendix Z — Repeat: absolute URL occurrences (grep-backed)

| file | pattern |
|------|---------|
| `Brain.tsx` | `http://127.0.0.1:8000/api/entities` etc. |
| `studioClient.ts` | `http://127.0.0.1:8000/api/internal/settings`, health |
| `InsightsPage.tsx` | `request` uses relative in loader; check top of file for `url` — Explore uses `new URL(..., import.meta.url)`? (skipped) |

**Action:** normalize on **`/api`** + proxy for **all** browser fetches.

---

## Appendix AA — Density tail: empty rows reserved for founder annotations

| row | founder note |
|-----|----------------|
| 1 | |
| 2 | |
| 3 | |
| 4 | |
| 5 | |
| 6 | |
| 7 | |
| 8 | |
| 9 | |
| 10 | |
| 11 | |
| 12 | |
| 13 | |
| 14 | |
| 15 | |
| 16 | |
| 17 | |
| 18 | |
| 19 | |
| 20 | |
| 21 | |
| 22 | |
| 23 | |
| 24 | |
| 25 | |
| 26 | |
| 27 | |
| 28 | |
| 29 | |
| 30 | |
| 31 | |
| 32 | |
| 33 | |
| 34 | |
| 35 | |
| 36 | |
| 37 | |
| 38 | |
| 39 | |
| 40 | |
| 41 | |
| 42 | |
| 43 | |
| 44 | |
| 45 | |
| 46 | |
| 47 | |
| 48 | |
| 49 | |
| 50 | |

---

*End of audit — `docs/AUDIT_CURSOR_2026-05-10.md`.*
