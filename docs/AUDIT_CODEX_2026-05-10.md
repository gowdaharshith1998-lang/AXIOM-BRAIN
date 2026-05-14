## 1. Database — what's actually there

Audit basis: `sqlite3 axiom.db ".tables"`, `sqlite3 axiom.db ".schema"`, `PRAGMA table_info`, and `SELECT COUNT(*)` per table. `axiom.db` already existed, so the dev server was not started to materialize it. The table list below is the actual on-disk database before any runtime-copy checks.

| Table | Columns | Rows | Example rows |
|---|---:|---:|---|
| `actions` | 8 | 0 | empty |
| `alembic_version` | 1 | 1 | `version_num=b2c3d4e5f6a7` |
| `edges` | 6 | 26,536 | 3 shown below |
| `entities` | 8 | 5,829 | 3 shown below |
| `metrics_snapshots` | 10 | 1 | `2026-05-10`: entities `5829`, edges `25068`, receipts `6`, agents `1` |
| `receipts` | 18 | 6 | 3 shown below |
| `receipts_legacy_20260510073931689096` | 7 | 0 | empty |
| `secrets` | 8 | 2 | 2 shown below, encrypted values redacted |
| `skills` | 9 | 0 | empty |
| `sources` | 7 | 0 | empty |

| Table | Column detail |
|---|---|
| `actions` | `id`, `agent_id`, `tool`, `params`, `decision`, `result_hash`, `task_id`, `created_at` |
| `alembic_version` | `version_num` |
| `edges` | `id`, `source_id`, `target_id`, `relationship`, `data`, `created_at` |
| `entities` | `id`, `type`, `data`, `source_id`, `created_at`, `updated_at`, `cluster_id`, `composite_importance` |
| `metrics_snapshots` | `id`, `snapshot_date`, `entity_count`, `edge_count`, `receipt_count`, `allow_count`, `correct_count`, `deny_count`, `agent_count`, `created_at` |
| `receipts` | `id`, `action_id`, `agent_name`, `intent`, `target_entity_id`, `cluster_id`, `decision`, `reason`, `policy_id`, `guidance`, `suggested_alternative`, `signing_scheme`, `signature`, `prev_hash`, `this_hash`, `calibra_state`, `demo_flag`, `created_at` |
| `receipts_legacy_20260510073931689096` | `id`, `receipt_type`, `merkle_leaf_index`, `created_at`, `payload`, `signature_ed25519_b64`, `signature_mldsa_b64` |
| `secrets` | `id`, `provider_id`, `key_name`, `encrypted_value`, `status`, `last_tested_at`, `created_at`, `updated_at` |
| `skills` | `id`, `skill_id`, `version`, `scope`, `skill_hash`, `process_entity_id`, `emitted_at`, `signed_metadata`, `markdown` |
| `sources` | `id`, `source_type`, `display_name`, `connected`, `created_at`, `updated_at`, `metadata` |

| Table | Example 1 |
|---|---|
| `edges` | `019dff227c8e7f52988bc698090e9a09`: `019dff227abb76538c770dace0b747e6` -> `019dff227b82771199702da3d376f180`, relationship `DECISION_REFERENCES_THREAD`, data `{}`, created `2026-05-06 21:12:23.438073` |
| `edges` | `019dff227c94796092a627a3082dc2b0`: `019dff227abb76538c770dace0b747e6` -> `019dff227aeb7f30baf4de5c5d6f547d`, relationship `DECISION_REFERENCES_DOCUMENT`, data `{}`, created `2026-05-06 21:12:23.444124` |
| `edges` | `019dff227c987401a1d17c64fbf8719d`: `019dff227b3272e1b548ffcad309f423` -> `019dff227b82771199702da3d376f180`, relationship `PERSON_PARTICIPATES_IN_THREAD`, data `{}`, created `2026-05-06 21:12:23.448964` |
| `entities` | `019dff227a3170738ccd0996cd578a4a`: type `code`, `file_path=src/axiom/ingest/pipeline.py`, `kind=file`, `language=python`, source `synthetic-default`, cluster `engineering_code`, importance `0.200995479766621` |
| `entities` | `019dff227aa27f40bebbe40a9fca35cd`: type `code`, `file_path=src/axiom/studio/server.py`, `kind=module`, `language=typescript`, source `synthetic-default`, cluster `engineering_code`, importance `0.200995479767944` |
| `entities` | `019dff227aa77cc0b18de77e1b66a84d`: type `code`, `file_path=src/axiom/storage/crud.py`, `kind=file`, `language=python`, source `synthetic-default`, cluster `engineering_code`, importance `0.200995479768605` |
| `receipts` | `65cfe9c9d3e791597dd2ae35a3afe70ea3de8476c3a6ece526cb89a858497c65`: action `act_8893e9688eba`, agent `smoke_agent`, intent `read`, cluster `external_mcp`, decision `allow`, policy `AEGIS-1`, signing `ml_dsa_65`, prev hash null, this hash `24a15d...659bd`, demo `1` |
| `receipts` | `cdd9a40b56d5370d8939b94c7efbd8c77574cf628c39e8ad9d31f1391a86d606`: action `act_a2ae60c6ba88`, agent `smoke_agent`, intent `read`, cluster `external_mcp`, decision `allow`, policy `AEGIS-1`, signing `hybrid`, prev hash `24a15d...659bd`, this hash `099fcd...62513`, demo `1` |
| `receipts` | `37695599efac3cbfac23ea20afbde8c032943ae97f2158e5cdce4583e795e3c1`: action `act_dd4ae221fac3`, agent `smoke_agent`, intent `read`, cluster `external_mcp`, decision `allow`, policy `AEGIS-1`, signing `ed25519`, prev hash `099fcd...62513`, this hash `8d856d...c09a0`, demo `1` |
| `secrets` | `019e0e7621717d93a0d41f8dafd62463`: provider `openai`, key `default`, encrypted value present and redacted, status `valid`, last tested `2026-05-09 20:44:00.511461` |
| `secrets` | `019e0e79e9167f80858cd9776d6bd79f`: provider `github`, key `default`, encrypted value present and redacted, status `valid`, last tested `2026-05-10 02:43:13.367380` |

Ground truth notes:

| Finding | Evidence |
|---|---|
| The current DB does not contain `agent_passports`, `passport_credentials`, `agent_registry`, `skill_runs`, `watchdog_alerts`, `cluster_check_runs`, `llm_provider_keys`, or `entity_embeddings` in the initial `.tables` output. | They are not listed by `sqlite3 axiom.db ".tables"`; `create_app()` would create some of these if the server starts. |
| `skills` table exists but is the old emitted-skill schema, not the runtime registry schema expected by current `src/axiom/skills/registry.py`. | Current DB has columns `skill_id`, `version`, `scope`, `skill_hash`, `markdown`; current code expects richer skill registry columns and creates/extends on startup. |
| Current on-disk `actions` table is empty. | `SELECT COUNT(*) FROM actions` returned `0`. |
| Current on-disk `sources` table is empty even though many entities have `source_id='synthetic-default'`. | `SELECT COUNT(*) FROM sources` returned `0`; entity examples reference `synthetic-default`. |
| Current on-disk receipts are all demo/smoke records. | First 3 rows show `agent_name=smoke_agent`, `demo_flag=1`. |

## 2. Endpoints — what's exposed

Audit basis: route grep in `src/axiom/studio/server.py`; requested `mcp/server.py` does not exist. Actual MCP module is `src/axiom/mcp/server.py`; it exposes FastMCP tools, not FastAPI routes. `src/axiom/studio/server.py` also includes `vault_router` and `llm_keys_router`, so those routes are exposed at runtime even though they are in separate files.

| Method | Path | Handler | What it returns | Frontend call? |
|---|---|---|---|---|
| `GET` | `/api/health` | `health` | status, current WebSocket seq, live flag, events emitted | Yes: `studioClient.getHealth()` absolute URL; settings status |
| `GET` | `/api/internal/settings` | `get_studio_settings` | `{settings}` from `app.state.studio_settings` | Yes: `studioClient.getStudioSettings()` |
| `PUT` | `/api/internal/settings` | `put_studio_settings` | merged `{settings}` and writes `axiom_studio_settings.json` | Yes: `studioClient.saveStudioSettings()` |
| `GET` | `/api/internal/agent-registry` | `get_agent_registry` | `{agents, range_days, type}` enriched with latest passport info | Yes: `agentsClient.listAgentRegistry()` |
| `POST` | `/api/internal/agent-registry` | `post_agent_registry` | one registry row plus passport fields and maybe bearer token | Yes: `agentsClient.registerAgent()` |
| `GET` | `/api/internal/mcp-stats` | `get_mcp_stats` | tool call counters, active agents, recent buffered MCP actions | Yes: `studioClient.getMcpStats()` |
| `POST` | `/api/internal/passports` | `post_internal_passport` | passport dict plus one-time bearer token | Yes: `passportsClient.issuePassport()` |
| `GET` | `/api/internal/passports` | `get_internal_passports` | `{passports}` from `passport_to_dict` | Yes: `passportsClient.listPassports()` |
| `GET` | `/api/internal/passports/{passport_id}` | `get_internal_passport` | one passport dict or 404 | No direct frontend grep hit |
| `DELETE` | `/api/internal/passports/{passport_id}` | `delete_internal_passport` | revoked passport dict | Yes: `passportsClient.revokePassport()` |
| `POST` | `/api/internal/passports/{passport_id}/kill-switch` | `post_internal_passport_kill_switch` | toggled passport dict | Yes: `passportsClient.setPassportKillSwitch()` |
| `GET` | `/api/internal/metrics-snapshots` | `get_metrics_snapshots` | `{snapshots, range_days}` and may take a snapshot if enabled | No direct frontend grep hit |
| `GET` | `/api/internal/cluster-checks` | `get_internal_cluster_checks` | paged cluster check run rows | No direct frontend grep hit |
| `GET` | `/api/internal/cluster-checks/summary` | `get_internal_cluster_checks_summary` | cluster summary, 24h window | No direct frontend grep hit |
| `GET` | `/api/internal/watchdog/alerts` | `get_internal_watchdog_alerts` | `{alerts}` filtered by status/cluster/limit | Yes: `watchdogClient`, `AIInsightCard` |
| `POST` | `/api/internal/watchdog/alerts/{alert_id}/acknowledge` | `post_internal_watchdog_acknowledge` | acknowledged alert dict | Yes: `watchdogClient.acknowledgeWatchdogAlert()` |
| `POST` | `/api/internal/watchdog/alerts/{alert_id}/resolve` | `post_internal_watchdog_resolve` | resolved alert dict | Yes: `watchdogClient.resolveWatchdogAlert()` |
| `GET` | `/api/internal/skills` | `get_internal_skills` | `{skills}` filtered by status/intent | Yes: `skillsClient.listSkills()` |
| `GET` | `/api/internal/skills/{skill_id}` | `get_internal_skill` | one skill dict | No direct frontend grep hit |
| `GET` | `/api/internal/skills/{skill_id}/runs` | `get_internal_skill_runs` | `{runs}` recent skill runs | Yes: `skillsClient.listSkillRuns()` |
| `POST` | `/api/internal/skills` | `post_internal_skill` | registered skill dict and publishes `skill_registered` | Yes: `skillsClient.registerSkill()` |
| `POST` | `/api/internal/skills/{skill_id}/activate` | `post_internal_skill_activate` | activated skill dict | No direct frontend grep hit |
| `POST` | `/api/internal/skills/{skill_id}/run` | `post_internal_skill_run` | skill run result from runner | No direct frontend grep hit; there is no run button in `SkillsPage` |
| `POST` | `/api/internal/skills/{skill_id}/archive` | `post_internal_skill_archive` | archived skill dict and publishes `skill_archived` | Yes: `skillsClient.archiveSkill()` |
| `GET` | `/api/entities` | `get_entities` | all entities as DTO dicts | Yes: `Brain.tsx` bootstrap |
| `GET` | `/api/cluster_health` | `get_cluster_health` | per-cluster health plus `overall` | Yes: `Brain.tsx`, health UI |
| `GET` | `/api/sources` | `get_sources` | synthetic source snapshot | Yes: page loaders use generic fetch URLs |
| `GET` | `/api/entities/search` | `search_entities_endpoint` | ranked `EntitySearchResult[]` | Yes: `ExplorePage` / `InsightsPage` generic fetch pattern |
| `POST` | `/api/internal/search` | `post_internal_search` | hybrid/lexical/semantic/graph search result dict | Yes: `CommandPalette` |
| `GET` | `/api/edges` | `get_edges` | all edges as DTO dicts | Yes: `Brain.tsx` bootstrap |
| `GET` | `/api/governance` | `get_governance` | combined governance snapshot, policies, checks, receipts, audit events, lineage | Yes: `GovernancePage` |
| `GET` | `/api/internal/receipts` | `get_internal_receipts` | `{receipts, total_count, merkle_head}` | Yes: `agentsClient.listAgentReceipts()` |
| `GET` | `/api/internal/receipts/{receipt_id}` | `get_internal_receipt` | one receipt row plus `verification_status` | No direct frontend grep hit |
| `GET` | `/api/internal/merkle-status` | `get_internal_merkle_status` | chain length, head/tail hashes, signing scheme distribution | No direct frontend grep hit |
| `WS` | `/ws/brain` | `ws_brain` | sequenced broadcaster envelopes with replay from `since` | Yes: `BrainWebSocket`, `PassportsPage` raw socket |
| `POST` | `/api/internal/agent-navigation` | `publish_agent_navigation` | `{emitted}` and publishes `agent_navigation_step` events | No frontend fetch; MCP forwarder posts here |
| `POST` | `/api/internal/agent-action-events` | `publish_agent_action_events` | `{emitted}` and publishes incoming event types | No frontend fetch; MCP forwarder posts here |

Exposed via included routers, not in the two files named by the prompt:

| Method | Path | Source file | What it returns | Frontend call? |
|---|---|---|---|---|
| `GET` | `/api/providers` | `studio/vault_api.py` | provider metadata list | Yes: `vaultClient.listProviders()` |
| `GET` | `/api/providers/{provider_id}` | `studio/vault_api.py` | one provider metadata object | Yes: `vaultClient.getProvider()` |
| `GET` | `/api/secrets` | `studio/vault_api.py` | secret metadata only | Yes: `vaultClient.listSecrets()` |
| `POST` | `/api/secrets` | `studio/vault_api.py` | stored secret metadata | Yes: `vaultClient.storeSecret()` |
| `DELETE` | `/api/secrets/{provider_id}/{key_name}` | `studio/vault_api.py` | `{deleted}` | Yes: `vaultClient.deleteSecret()` |
| `POST` | `/api/secrets/{provider_id}/{key_name}/test` | `studio/vault_api.py` | verification result and secret metadata | Yes: `vaultClient.testSecret()` |
| `PUT` | `/api/secrets/{provider_id}/{key_name}` | `studio/vault_api.py` | rotated secret metadata | Yes: `vaultClient.rotateSecret()` |
| `POST` | `/api/internal/llm-keys` | `studio/llm_keys_api.py` | saved LLM key metadata | Yes: `llmKeysClient.saveLLMKey()` |
| `GET` | `/api/internal/llm-keys` | `studio/llm_keys_api.py` | `{keys}` | Yes: `llmKeysClient.listLLMKeys()` |
| `DELETE` | `/api/internal/llm-keys/{provider}` | `studio/llm_keys_api.py` | delete result | Yes: `llmKeysClient.disconnectLLMKey()` |
| `POST` | `/api/internal/llm-keys/{provider}/test` | `studio/llm_keys_api.py` | tested LLM key metadata | Yes: `llmKeysClient.testLLMKey()` |
| `GET` | `/api/internal/llm-keys/{provider}` | `studio/llm_keys_api.py` | one LLM key metadata | No direct frontend grep hit |

Actual MCP tools in `src/axiom/mcp/server.py`, not FastAPI routes:

| Tool | Handler | What it returns / does |
|---|---|---|
| `axiom_query_brain` | `axiom_query_brain` | search results with 1-hop expansion |
| `axiom_get_entity` | `axiom_get_entity` | entity detail and optional neighbors |
| `axiom_traverse` | `axiom_traverse` | BFS traversal result |
| `axiom_list_sources` | `axiom_list_sources` | source list from DB/synthetic snapshot |
| `axiom_record_action` | `axiom_record_action` | policy-evaluated action receipt or ToolError on deny/correct gates |
| `axiom_check_policy` | `axiom_check_policy` | preflight policy evaluation, no persistence |
| `axiom_request_human_approval` | `axiom_request_human_approval` | in-memory approval queue item/status |
| `axiom_list_skills` | `axiom_list_skills` | registered skills list |
| `axiom_get_skill` | `axiom_get_skill` | one skill by id |
| `axiom_run_skill` | `axiom_run_skill` | skill run result, with policy preflight |
| `axiom_register_skill` | `axiom_register_skill` | created skill, with policy preflight |
| `axiom_archive_skill` | `axiom_archive_skill` | archived skill, with policy preflight |

## 3. Frontend API calls — what's actually fetched

Audit basis: `rg -n "fetch\(|axios|new WebSocket|EventSource|WebSocket" frontend/src`. No axios usage was found.

| File:line | URL / path | Method | Where response goes |
|---|---|---|---|
| `frontend/src/components/Brain.tsx:46` | variable `url`; used for `/api/entities`, `/api/edges`, `/api/cluster_health` | GET | bootstrap graph entities/edges/health into brain store and 3D scene |
| `frontend/src/components/AIInsightCard.tsx:21` | `/api/internal/watchdog/alerts?status=open&limit=50` | GET | highest-severity open alert rendered in AI insight card |
| `frontend/src/components/CommandPalette.tsx:164` | `/api/internal/search` | POST | search results list; selected result updates store and dispatches `axiom:fly-to-entity` |
| `frontend/src/pages/ExplorePage.tsx:37` | variable `url` | GET | page-specific entity/result lists |
| `frontend/src/pages/InsightsPage.tsx:20` | variable `url` | GET | insights page data loaders |
| `frontend/src/pages/GovernancePage.tsx:135` | `/api/governance` | GET | governance snapshot state for overview/policies/checks/receipts/lineage/audit tabs |
| `frontend/src/lib/watchdogClient.ts:4` | caller-provided `path` | mixed | JSON helper for watchdog calls |
| `frontend/src/lib/watchdogClient.ts:17` | `/api/internal/watchdog/alerts?status=<status>&limit=50` | GET | `listWatchdogAlerts()` returns `data.alerts` |
| `frontend/src/lib/watchdogClient.ts:24` | `/api/internal/watchdog/alerts/<id>/acknowledge` | POST | returns updated alert |
| `frontend/src/lib/watchdogClient.ts:34` | `/api/internal/watchdog/alerts/<id>/resolve` | POST | returns resolved alert |
| `frontend/src/lib/skillsClient.ts:42` | caller-provided `path` | mixed | JSON helper for skill calls |
| `frontend/src/lib/skillsClient.ts:54` | `/api/internal/skills` | GET | `listSkills()` returns `data.skills` |
| `frontend/src/lib/skillsClient.ts:59` | `/api/internal/skills` | POST | `registerSkill()` returns created skill |
| `frontend/src/lib/skillsClient.ts:66` | `/api/internal/skills/<id>/archive` | POST | `archiveSkill()` returns archived skill |
| `frontend/src/lib/skillsClient.ts:73` | `/api/internal/skills/<id>/runs` | GET | `listSkillRuns()` returns `data.runs` |
| `frontend/src/lib/agentsClient.ts:43` | caller-provided `path` | mixed | JSON helper for agent calls |
| `frontend/src/lib/agentsClient.ts:55` | `/api/internal/agent-registry` | GET | `listAgentRegistry()` returns `data.agents` |
| `frontend/src/lib/agentsClient.ts:60` | `/api/internal/agent-registry` | POST | `registerAgent()` returns created/enriched row |
| `frontend/src/lib/agentsClient.ts:68` | `/api/internal/receipts?agent=<name>&limit=20` | GET | drawer recent receipt rows |
| `frontend/src/lib/passportsClient.ts:34` | caller-provided `path` | mixed | JSON helper for passport calls |
| `frontend/src/lib/passportsClient.ts:46` | `/api/internal/passports?active_only=false` | GET | `listPassports()` returns `data.passports` |
| `frontend/src/lib/passportsClient.ts:51` | `/api/internal/passports` | POST | `issuePassport()` returns passport plus token |
| `frontend/src/lib/passportsClient.ts:58` | `/api/internal/passports/<id>` | DELETE | `revokePassport()` returns passport payload |
| `frontend/src/lib/passportsClient.ts:65` | `/api/internal/passports/<id>/kill-switch` | POST | `setPassportKillSwitch()` returns passport payload |
| `frontend/src/lib/llmKeysClient.ts:15` | caller-provided `path` | mixed | JSON helper for older LLM-key API |
| `frontend/src/lib/llmKeysClient.ts:36` | `/api/internal/llm-keys` | GET | `listLLMKeys()` returns `data.keys` |
| `frontend/src/lib/llmKeysClient.ts:41` | `/api/internal/llm-keys` | POST | `saveLLMKey()` returns metadata |
| `frontend/src/lib/llmKeysClient.ts:48` | `/api/internal/llm-keys/<provider>/test` | POST | `testLLMKey()` returns metadata |
| `frontend/src/lib/llmKeysClient.ts:54` | `/api/internal/llm-keys/<provider>` | DELETE | `disconnectLLMKey()` expects `{deleted}` |
| `frontend/src/lib/studioClient.ts:24` | caller-provided `url` | mixed | JSON helper for settings/MCP/health |
| `frontend/src/lib/studioClient.ts:30` | `http://127.0.0.1:8000/api/internal/settings` | GET | settings state |
| `frontend/src/lib/studioClient.ts:35` | `http://127.0.0.1:8000/api/internal/settings` | PUT | persisted settings state |
| `frontend/src/lib/studioClient.ts:44` | `/api/internal/mcp-stats` | GET | settings API/MCP stats panel |
| `frontend/src/lib/studioClient.ts:48` | `http://127.0.0.1:8000/api/health` | GET | health string for settings panel |
| `frontend/src/lib/vaultClient.ts:79` | caller-provided `path` | mixed | vault JSON/text helper with mapped errors |
| `frontend/src/lib/vaultClient.ts:104` | `/api/providers` | GET | provider cards |
| `frontend/src/lib/vaultClient.ts:110` | `/api/providers/<id>` | GET | one provider detail |
| `frontend/src/lib/vaultClient.ts:116` | `/api/secrets` | GET | settings vault secret metadata |
| `frontend/src/lib/vaultClient.ts:121` | `/api/secrets` | POST | stored secret metadata |
| `frontend/src/lib/vaultClient.ts:130` | `/api/secrets/<provider>/<key>` | DELETE | removes secret |
| `frontend/src/lib/vaultClient.ts:140` | `/api/secrets/<provider>/<key>/test` | POST | verification result and secret metadata |
| `frontend/src/lib/vaultClient.ts:149` | `/api/secrets/<provider>/<key>` | PUT | rotated secret metadata |
| `frontend/src/pages/PassportsPage.tsx:59` | `ws://<host>/ws/brain` or `wss://<host>/ws/brain` | WS | page-local passport updates on `passport_issued`, `passport_revoked`, `passport_kill_switch_toggled` |
| `frontend/src/lib/websocket.ts:69` | configured brain socket URL plus `?since=<lastSeq>` | WS | global brain event stream; dispatches handlers/status |

## 4. WebSocket events — fire vs listen

Audit basis: backend grep for `broadcaster.publish` in `src/axiom/studio/server.py` and `src/axiom/govern/watchdog.py`; extra event-producing modules are noted because the running app starts organizer/watchdog and MCP forwarders use the same stream. Frontend listener grep covered `state/brain.store.ts`, pages, components, and `particle-behaviors.ts`.

| Backend publishes | Frontend listens / handles |
|---|---|
| `cluster_health_changed` from Studio cluster health loop | Yes: `brain.store.ts`, `Brain.tsx` label refresh |
| `passport_issued` from passport issue and agent registration | Yes: `PassportsPage.tsx` only; not in global brain store |
| `passport_revoked` from passport delete | Yes: `PassportsPage.tsx` only |
| `passport_kill_switch_toggled` from kill switch endpoint | Yes: `PassportsPage.tsx` only |
| `watchdog_alert_acknowledged` from acknowledge endpoint | Yes: `brain.store.ts`, `GovernancePage.tsx` window-event handling |
| `watchdog_alert_resolved` from resolve endpoint | Yes: `brain.store.ts`, `GovernancePage.tsx`; store removes alert/insight on resolve |
| `skill_registered` from skill create | Yes: `SkillsPage.tsx`; typed in `websocket.ts` |
| `skill_archived` from skill archive | Yes: `SkillsPage.tsx`; typed in `websocket.ts` |
| `skill_run_started` via skill runner callback | Yes: `SkillsPage.tsx`; typed in `websocket.ts` |
| `skill_run_completed` via skill runner callback | Yes: `SkillsPage.tsx`; typed in `websocket.ts` |
| `skill_run_failed` via skill runner callback | **No** explicit frontend listener and not in `BrainEvent` union. Failed skill runs can be missed live. |
| `agent_navigation_step` from `/api/internal/agent-navigation` | Yes: `particle-behaviors.ts`; not stored in `brain.store.ts` |
| Dynamic type from `/api/internal/agent-action-events`, default `agent_action` | `agent_action` yes: `brain.store.ts`, `AgentsPage.tsx`; arbitrary dynamic types not guaranteed |
| `watchdog_alert_raised` from `WatchdogAgent._emit_alert` | Yes: `brain.store.ts`, `GovernancePage.tsx`, AI insight derivation |
| `insight_flagged` from watchdog and demo warden | Yes: `brain.store.ts` |
| `entity_added` from ingest pipeline outside requested files | Yes: `brain.store.ts`, `Brain.tsx`, `particle-behaviors.ts` |
| `edge_added` from ingest pipeline outside requested files | Yes: `brain.store.ts`, `Brain.tsx` |
| `entity_classified` from organizer outside requested files | Yes: `brain.store.ts`, `Brain.tsx` |
| `entity_edge_created` from edge proposer outside requested files | Yes: `brain.store.ts`, `Brain.tsx` |
| `confidence_changed` from organizer outside requested files | Yes: `particle-behaviors.ts`; not persisted in store |
| `agent_action_evaluated` from demo agent/MCP outside requested files | Yes: `brain.store.ts`, `particle-behaviors.ts` |
| `receipt_added` from demo agent/MCP outside requested files | Yes: `brain.store.ts`, `particle-behaviors.ts` |
| `agent_action_blocked` from MCP deny path | **No** global store listener; `BrainEvent` union does not include it. |
| `agent_action_corrected` from MCP correct path | **No** global store listener; `BrainEvent` union does not include it. |
| Frontend type union includes `entity_modified`, `entity_removed`, `edge_removed` | **Listened as type only**, but no `brain.store.ts` state handler found. |
| DESIGN mentions `policy_decision_made`, `receipt_emitted`, `agent_action_signed`, `approval_queue_updated`, `skill_emitted` | **No current backend publish in runtime grep and no current frontend listener.** |

## 5. Tests — what they actually prove

Commands run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest --collect-only -q -p no:cacheprovider` and `cd frontend && ./node_modules/.bin/vitest --run --reporter=verbose`. Pytest was collection-only, not execution. Vitest executed and passed `56` files / `312` tests. Pytest collected `343` tests and emitted warnings because plugin autoload was disabled, so `pytest.mark.asyncio` marks were unknown during collection.

| Test file | Count | Surface | Skeptical assessment |
|---|---:|---|---|
| `tests/test_agent_actions.py` | 4 | governance/events | Unit-level demo policy and payload shape; catches shape drift, not real UI/runtime auth regressions. |
| `tests/test_agent_navigation_events.py` | 3 | websocket/organizer | Catches navigation-event throttling; not a browser proof. |
| `tests/test_agent_passports.py` | 13 | passports/MCP | Good backend passport behavior coverage; frontend status mismatch still slipped through. |
| `tests/test_agent_registry.py` | 7 | agents/endpoints | Covers registry endpoints and stats; mostly synthetic/local. |
| `tests/test_broadcaster_phase_3.py` | 6 | websocket core | Strong core broadcaster behavior; not full app lifecycle. |
| `tests/test_cli_serve_live.py` | 3 | CLI/server | Checks CLI wiring and live flags; not production deploy. |
| `tests/test_cluster_check_runs.py` | 5 | db/endpoint | Covers cluster check persistence and filtering; local DB only. |
| `tests/test_cluster_health.py` | 7 | domain | Good deterministic health scoring; not UI truth. |
| `tests/test_confidence_changed_events.py` | 3 | organizer/events | Catches event threshold math; no frontend assertion. |
| `tests/test_correct_decision_branch.py` | 7 | policy | Covers demo CORRECT branch; not a real policy engine. |
| `tests/test_design_doc.py` | 4 | docs | Locks document presence/naming, not runtime behavior. |
| `tests/test_edge_proposer.py` | 4 | db/events | Useful edge proposer behavior tests; async warnings in collect-only run. |
| `tests/test_fixture_generator_phase_3.py` | 1 | fixture | Determinism only. |
| `tests/test_fixture_shape_phase_3.py` | 4 | fixture | Shape/invariant checks for synthetic data; no live connector proof. |
| `tests/test_ingest_pipeline_phase_3.py` | 4 | ingest/db/ws | Good pipeline round-trip coverage in isolation. |
| `tests/test_ledger_warden.py` | 6 | demo receipts/insights | Demo-only ledger/warden shape; not cryptographic verification. |
| `tests/test_live_synthetic_source.py` | 11 | synthetic source | Good generator behavior; no external source coverage. |
| `tests/test_llm_provider_keys.py` | 6 | LLM key API | Covers older LLM-key API; vault API is separate and more used by settings. |
| `tests/test_mcp_cli.py` | 1 | MCP CLI | Dispatch smoke only. |
| `tests/test_mcp_read_tools.py` | 16 | MCP read | Good read-tool and latency assertions, synthetic/local. |
| `tests/test_mcp_write_tools.py` | 19 | MCP write/governance | Strong backend write-tool coverage; frontend does not listen to blocked/corrected events. |
| `tests/test_metrics_snapshots.py` | 6 | db/endpoint | Snapshot behavior; not production scheduling. |
| `tests/test_migrations.py` | 1 | migrations | Upgrade/downgrade smoke; does not guarantee current `axiom.db` schema matches code before server startup. |
| `tests/test_neighbors.py` | 4 | graph | Graph traversal utility coverage. |
| `tests/test_organize_centrality.py` | 8 | organizer/math | Centrality math and DB update coverage. |
| `tests/test_organize_classifier.py` | 12 | classifier | Good keyword/LLM-fallback contract; no real LLM call required. |
| `tests/test_organizer_agent.py` | 8 | organizer/events | Covers loops/backfill in isolation. |
| `tests/test_phase_3_guards.py` | 2 | guardrails | Naming/import guardrails; not product behavior. |
| `tests/test_provider_router.py` | 11 | provider routing | Good key resolution fallbacks; no real provider integration. |
| `tests/test_providers.py` | 24 | provider verification | Good mocked verifier matrix; connector ingestion still absent. |
| `tests/test_receipts_phase_7.py` | 10 | receipts/db/endpoint | Good hash-chain persistence and verification; no detached signature/proof files. |
| `tests/test_retrieval_phase_8_6.py` | 18 | retrieval | Good lexical/semantic/graph RRF behavior; local embeddings only. |
| `tests/test_search_api.py` | 7 | endpoint/search | Good string ranking coverage; not command-palette browser E2E. |
| `tests/test_server_phase_3.py` | 6 | API/ws | Basic server endpoints and replay; not full current route surface. |
| `tests/test_skills_emitter.py` | 9 | skills/backend | Covers registry/runner with mocked LLM; real missing/invalid provider produces failed run. |
| `tests/test_sources_base_phase_3.py` | 2 | source ABC | Interface shape only. |
| `tests/test_storage.py` | 8 | db/crud | Core CRUD coverage. |
| `tests/test_storage_public_api.py` | 3 | storage API | Public storage facade coverage. |
| `tests/test_stubs.py` | 15 | stubs/guards | Locks stub behavior; many claims are still stubs or superseded. |
| `tests/test_synthetic_source_phase_3.py` | 4 | synthetic source | Fixture source behavior only. |
| `tests/test_vault.py` | 18 | vault/db | Good encrypted-secret unit coverage; no auth/tenancy. |
| `tests/test_vault_api.py` | 17 | vault endpoints | Good HTTP API coverage; still single-user dev per code TODO. |
| `tests/test_watchdog.py` | 16 | watchdog/db/endpoints | Good rule/endpoint coverage; AI card integration is frontend-tested separately, not full browser. |
| `frontend/src/__tests__/CommandPalette.test.tsx` | 10 | UI/search | Good component behavior with mocked fetch; proves dispatch, not live navigation in browser. |
| `frontend/src/__tests__/HUD.test.tsx` | 8 | UI | Store-backed HUD shape; not real rendering performance. |
| `frontend/src/__tests__/aegis-gate.test.ts` | 3 | UI/visual logic | Locks visual state math; not governance correctness. |
| `frontend/src/__tests__/aegis-particles.test.ts` | 3 | UI particles | Visual effect shape only. |
| `frontend/src/__tests__/ai-insight-card.test.tsx` | 4 | UI/watchdog | Good mocked alert binding; not proof watchdog event reached browser. |
| `frontend/src/__tests__/app-title.test.tsx` | 2 | UI shell | Shell smoke and hotkey guard. |
| `frontend/src/__tests__/arrival-effect.test.ts` | 5 | UI animation | Visual helper only. |
| `frontend/src/__tests__/auto-orbit.test.ts` | 3 | UI camera | Camera math only. |
| `frontend/src/__tests__/brain-envelope-lobes.test.ts` | 3 | UI layout | Layout integration expectations. |
| `frontend/src/__tests__/brain-envelope.test.ts` | 3 | UI layout | Deterministic positioning only. |
| `frontend/src/__tests__/brain.store.test.ts` | 9 | state/ws | Good event reducer tests; misses `skill_run_failed`, blocked/corrected. |
| `frontend/src/__tests__/brand-mark.test.tsx` | 2 | UI | Branding smoke. |
| `frontend/src/__tests__/camera-flyto.test.ts` | 4 | UI camera | Fly-to math and cancellation; no actual canvas proof. |
| `frontend/src/__tests__/camera-reset.test.ts` | 3 | UI keyboard | Reset hotkey behavior. |
| `frontend/src/__tests__/chrome-rebuild.test.tsx` | 7 | UI shell | Good shell component smoke; mocked store. |
| `frontend/src/__tests__/cluster-aura.test.ts` | 12 | UI visual | Aura geometry/material expectations. |
| `frontend/src/__tests__/cluster-bracket-label.test.tsx` | 7 | UI visual | Label formatting/positioning. |
| `frontend/src/__tests__/cluster-force-layout.test.ts` | 1 | UI layout | Minimal determinism. |
| `frontend/src/__tests__/cluster-hub-icon.test.ts` | 3 | UI visual | Icon mapping only. |
| `frontend/src/__tests__/cluster-label-collision.test.ts` | 3 | UI layout | Collision resolver math. |
| `frontend/src/__tests__/cluster-layout.test.ts` | 16 | UI layout | Strong layout helper coverage. |
| `frontend/src/__tests__/cluster-mesh.test.ts` | 4 | UI graph | Intra-cluster edge helper coverage. |
| `frontend/src/__tests__/curved-conduits.test.ts` | 7 | UI visual | Conduit geometry/material logic. |
| `frontend/src/__tests__/edge-animation.test.ts` | 3 | UI animation | Edge animation math. |
| `frontend/src/__tests__/edge-shimmer.test.ts` | 1 | UI animation | Narrow shimmer bound. |
| `frontend/src/__tests__/edge-style.test.ts` | 4 | UI visual | Edge material switch behavior. |
| `frontend/src/__tests__/edge-tint.test.ts` | 2 | UI visual | Relationship color mapping. |
| `frontend/src/__tests__/export.test.ts` | 3 | UI/export | Export helper only. |
| `frontend/src/__tests__/fps-guard.test.ts` | 5 | UI performance logic | Budget state machine; not actual FPS. |
| `frontend/src/__tests__/fps.test.ts` | 1 | UI performance logic | Windowing helper only. |
| `frontend/src/__tests__/hex-geometry.test.ts` | 2 | UI geometry | Prism geometry only. |
| `frontend/src/__tests__/hex-layout.test.ts` | 12 | UI layout | Good static layout expectations. |
| `frontend/src/__tests__/idle-orbit.test.ts` | 5 | UI camera | Idle orbit logic. |
| `frontend/src/__tests__/idle-pulse.test.ts` | 3 | UI animation | Pulse helper only. |
| `frontend/src/__tests__/inspector.test.tsx` | 5 | UI inspector | Proves selected entity overview rendering in test, not browser click. |
| `frontend/src/__tests__/labels.test.ts` | 26 | UI labels | Good label utility coverage. |
| `frontend/src/__tests__/lod.test.ts` | 8 | UI performance logic | LOD rule coverage; not live GPU proof. |
| `frontend/src/__tests__/palette.test.ts` | 3 | UI colors | Palette invariants. |
| `frontend/src/__tests__/particle-behaviors.test.ts` | 11 | UI/ws particles | Covers event-to-effect mapping, including `agent_action_evaluated`; misses `agent_action_blocked`. |
| `frontend/src/__tests__/particle-flow.test.ts` | 8 | UI particles | Particle flow behavior. |
| `frontend/src/__tests__/passports-page.test.tsx` | 9 | UI/passports | Good mocked UI; mocks include `status`, while real passport endpoint lacks `status`. |
| `frontend/src/__tests__/phase-13b-ui.test.tsx` | 16 | UI agents/skills/watchdog | Good mocked Phase 13 UI; does not hit real backend. |
| `frontend/src/__tests__/radial-traffic.test.ts` | 5 | UI particles | Radial traffic visual logic. |
| `frontend/src/__tests__/reactive-spawn.test.ts` | 2 | UI animation | Spawn config only. |
| `frontend/src/__tests__/reconnect-hud.test.tsx` | 3 | UI/ws | Connection-status display with mocked state. |
| `frontend/src/__tests__/renderer-kind.test.ts` | 1 | UI renderer detection | Narrow helper. |
| `frontend/src/__tests__/satellite-pack.test.ts` | 3 | UI layout | Determinism and bounds. |
| `frontend/src/__tests__/settings-page.test.tsx` | 7 | UI/settings | Good mocked settings/vault flow; no real auth. |
| `frontend/src/__tests__/sphere-geometry.test.ts` | 2 | UI geometry | Sphere geometry only. |
| `frontend/src/__tests__/spoke-shimmer.test.ts` | 5 | UI animation | Shimmer bounds. |
| `frontend/src/__tests__/synaptic-flow.test.ts` | 6 | UI particles | Particle count/position rules. |
| `frontend/src/__tests__/vault-client.test.ts` | 11 | frontend API client | Good path/error mapping. |
| `frontend/src/__tests__/webgpu-detect.test.ts` | 1 | UI renderer detection | Narrow helper. |
| `frontend/src/__tests__/websocket.test.ts` | 3 | frontend WS client | Reconnect/since/status behavior with mocked WebSocket. |
| `frontend/src/components/__tests__/phase_stub.test.ts` | 1 | UI stub | Confirms stub throws. |
| `frontend/src/hooks/__tests__/useBrainFocus.test.ts` | 8 | UI focus state | Good focus/hash behavior. |

## 6. Dead code

Grep-based pass used basename references across `src/`, `frontend/src/`, and `tests/`. This is heuristic: it catches obviously unreferenced modules but can miss dynamic imports and can false-positive on shared names.

| Path | Suspected reason |
|---|---|
| `frontend/src/components/BrainCanvas.tsx` | Exports `BrainCanvas()` that always throws/never returns; no references found. Looks like old stub. |
| `frontend/src/components/HexGridBackground.tsx` | Exports component and re-export for `createHexGridPlane`; no references by basename. Likely superseded visual experiment. |
| `frontend/src/components/settings/SectionHeader.tsx` | Settings page uses local layout components instead; no references found. |
| `frontend/src/lib/particles/agent-effects.ts` | Particle effect system not imported; current visual stack uses other particle controllers. |
| `frontend/src/lib/particles/idle-pulse-runner.ts` | Idle pulse runner class not imported; idle-pulse helpers tested separately. |
| `frontend/src/lib/particles/nebula-bg.ts` | Nebula background factory not imported. |
| `frontend/src/lib/particles/orbital-halo.ts` | Orbital halo class not imported. |

No Python file in `src/` was flagged by this basename-only zero-reference pass. That does not prove all Python is live; it only means this grep heuristic found no obvious orphan modules.

## 7. End-to-end flows that work

Runtime mutation checks were executed against temporary SQLite copies, not the real `axiom.db`, to respect the read-only constraint. Evidence command family: direct route invocation from `create_app(db_url=sqlite:////tmp/axiom_audit_runtime*.db, enable_organizer=False)` plus SQLAlchemy checks against the temp DB. This is runtime code, not test mocks, but it is not a browser E2E.

| Flow | Status | Evidence |
|---|---|---|
| Ingest synthetic entity -> brain renders -> click -> inspector shows it | PARTIAL | Runtime route evidence: `/api/entities` returned `5829`, `/api/edges` returned `26536`, first entity `019dff227a3170738ccd0996cd578a4a`, type `code`, cluster `engineering_code`. Frontend evidence: `Brain.tsx` fetches entities/edges; `inspector.test.tsx` passed. Missing evidence: no actual browser click was run; no new synthetic ingest was executed because real DB is read-only and current app has no UI ingest endpoint. |
| Issue passport -> see in `/passports` UI -> revoke | PARTIAL | Runtime temp evidence: issue returned `bearer_token_present=true`, listed after issue `true`, revoke set `revoked_at_after_revoke=2026-05-11T08:21:46.544541`. Broken contract: real issue/list/revoke payloads did **not** include `status`, while frontend `Passport` type and tests expect `status`. Browser UI not run. |
| Register agent via UI -> row appears -> websocket reflects new action | PARTIAL | Runtime temp evidence: register returned `registered_agent_name=audit-agent`, registry list contained it, posting `/api/internal/agent-action-events` emitted `1`, broadcaster seq advanced `3 -> 4`, and `/api/internal/mcp-stats` showed recent action `audit-action-1`. Caveat: registering the agent itself does not publish an `agent_registered` event; websocket reflection requires a separate `agent_action` event. |
| Register skill via UI -> row appears -> run it -> see output | BROKEN/PARTIAL | Runtime direct runner evidence: registered skill id `019e16227acc7493bc994546138cf31a`; run status `failed`; error `unknown LLM provider: 'missing_provider'`; `runs_count=1`; `receipt_id=null`. Frontend has no `runSkill()` client function and no run button in `SkillsPage`; only registers, archives, and displays runs. Failed event `skill_run_failed` is not listened for by frontend. |
| Search Cmd-K palette -> results render -> click -> navigate | PARTIAL/WORKS | Runtime temp evidence: `/api/internal/search` query `refund`, mode `hybrid`, top_k `3` returned `3` results; first result title `Refund Policy 2026 (v3)`, methods `lexical, graph`. Frontend tests passed for result rendering, Enter selection, store `selectedId`, and `axiom:fly-to-entity` dispatch. Browser click not run. |
| Watchdog detects -> alert appears in AI INSIGHT card -> ack -> resolved | PARTIAL | Runtime temp evidence: inserted billing temp entity triggered alert id `019e16227ecd7001aa07a243f2c68af3`, rule `R1`, open count `1`; ack returned status `acknowledged`; resolve returned status `resolved`; resolved list contained it. Frontend `AIInsightCard` fetches open alerts and tests passed with mocked data. Browser card was not opened. |
| Receipt chain -> verify hash continuity in `/governance` | PARTIAL | Runtime temp evidence: `/api/internal/receipts/{id}` returned `verification_status=verified`; SQL continuity check over receipts returned `true`; `/api/internal/merkle-status` chain length `6`; `/api/governance` had current Merkle root. Caveat: `/governance` frontend only fetches `/api/governance`; it does not call the per-receipt verification endpoint or expose a continuity proof. |
| Policy gate -> action denied -> reason shown | PARTIAL | Runtime MCP service evidence: `record_action(intent=write, target_entity_id=audit_policy_billing)` raised ToolError `no decision document references this skill (policy_id=AEGIS-2)`; latest receipt decision `deny`, reason `no decision document references this skill`. Caveat: frontend does not listen for `agent_action_blocked` / `agent_action_corrected`, so live UI reason display is not proven. |

## 8. Claimed but not working

Claims below are tied to flows marked PARTIAL or BROKEN above.

| Claim source | Claim | Reality from section 7 |
|---|---|---|
| `README.md:19` | Frontend is a `React + Three.js 3D graph ... driven by live REST bootstrap + WebSocket updates`. | REST bootstrap works; no browser click/render proof was run in this audit; new ingest-to-click flow remains PARTIAL. |
| `README.md:20` | `⌘K command palette: Debounced search wired to backend ranking`. | Backend search and component tests work; browser click/navigation was not run. PARTIAL/WORKS, not full E2E. |
| `README.md:23` | `no MCP server or executable agent skills in this repo today`. | Stale claim: MCP server and skills registry/runner now exist. But skill UI still cannot run a skill, and a real run can fail without provider setup. |
| `README.md:23` | `Some UI and websocket traffic simulates agent actions and receipts for demo atmosphere; that is not verified governance.` | Still directionally true for UI. Backend receipts verify hash chain; UI governance page does not verify continuity. |
| `DESIGN.md:14` | Governance emits `verifiable receipts for every agent action`. | MCP deny path writes a deny receipt, but not every UI/system action is gated; frontend does not display blocked/corrected live events. |
| `DESIGN.md:16` | Humans supervise approvals and corrections visible as receipts. | Receipt lists exist, but approval queue has no durable UI and correction/blocked events are not handled by global store. |
| `DESIGN.md:20` | Hosted production from day 1, URL partners can click. | No hosted deployment config or reliable hosted demo in repo; README says run locally. |
| `DESIGN.md:601-603` | `axiom_verify_receipt` verifies detached signatures + Merkle inclusion proof. | Current runtime verified DB hash-chain continuity; no detached `.sig` or Merkle inclusion proof route/tool was evidenced. |
| `docs/AXIOM_PHASE_5_12_SPEC.md:317-318` | `Every action is checked, signed, and auditable`. | MCP write actions are policy-gated; UI actions/settings/passport flows are not all signed governance actions. |
| `docs/AXIOM_PHASE_5_12_SPEC.md:680-681` | Acceptance requires query surface and inspector click with real data. | Tests cover components; audit did not prove a live browser click-to-inspector path. |
| Commit `a013129` | `phase 13.b: skills + agents forms + watchdog feed panel`. | Forms/feed exist; skill run is not exposed in frontend and failed-run event is not listened for. |
| Commit `eeccf4e` | `watchdog agent + 6 detection rules + real ai insight binding`. | Watchdog detection/ack/resolve works in backend; AI card binding is component-tested/mocked, not browser-proven. |
| Commit `d2cae7f` | `passport ui + key vault wiring + search mode toggle`. | Passport backend issue/revoke works, but real passport payloads lack `status` field expected by UI type/tests. |
| Commit `c2cf8be` | `persistent receipts table + merkle hash chain`. | Hash chain exists and verifies via internal endpoint; `/governance` UI does not verify continuity itself. |

## 9. Never built

Roadmap source: `docs/ROADMAP.md`. Cross-reference command: grep for phase terms against `src/`, `frontend/src/`, `.github`. “Zero code anchor” means no implementation class/module/route/config was found beyond docs, provider metadata, or explicit stubs.

| Roadmap item | Roadmap lines | Code anchor status |
|---|---|---|
| Hosted production deployment from day 1 | `docs/ROADMAP.md:68-76`, `docs/ROADMAP.md:285-299` | No `render.yaml`, `fly.toml`, `vercel.json`, `wrangler`, `Dockerfile`, or deployment workflow found. README says no reliable hosted demo URL. |
| Linear connector as first real connector | `docs/ROADMAP.md:78-85`, `docs/ROADMAP.md:302-314` | No `LinearSource`, no `src/axiom/sources/linear*`, no Linear ingest/watch implementation. |
| Slack/Gmail/Drive/GitHub source connectors | `docs/ROADMAP.md:28`, `docs/ROADMAP.md:85`, `docs/ROADMAP.md:316-330` | No `SlackSource`, `GmailSource`, `DriveSource`, `GitHubSource`. Provider verification/vault metadata exists, but ingestion connectors do not. |
| OAuth callback flow | `docs/ROADMAP.md:69-74`, `DESIGN.md:849-851` | Only OAuth provider stubs and provider metadata exist; no callback route implementation. |
| Calibra integration | `docs/ROADMAP.md:94-98`, `DESIGN.md:1137-1143` | No `calibra` import in `src/`; tests explicitly guard no Calibra imports. Metadata placeholders only. |
| PAUSE mode from uncertain beliefs | `docs/ROADMAP.md:32-33`, `DESIGN.md:622-634` | No Calibra-backed uncertainty gate; policy evaluator has allow/correct/deny demo logic only. |
| Post-quantum real signing and detached receipt files | `docs/ROADMAP.md:270-283`, `DESIGN.md:346-348` | DB hash-chain and demo signing scheme strings exist; no filesystem mirror at `~/.axiom/receipts`, detached `.sig`, or inclusion proof implementation evidenced. |
| Public production auth/basic signup gate | `docs/ROADMAP.md:73-74`, `docs/ROADMAP.md:420-423` | `vault_api.py` explicitly has TODO for authentication before multi-tenant; no auth middleware/tenant model found. |
| Multi-tenant/project isolation | `docs/ROADMAP.md:420-423` | Only disabled UI hint “Phase 11 — multi-tenant”; no tenant/project schema or auth guard. |
| Brain-specific `/api/brain/...` CRUD/query/preflight routes | `docs/AXIOM_COMPANY_BRAIN_AUDIT.md:224-238` | No `/api/brain` route anchor found in `src/`; current API uses `/api/entities`, `/api/edges`, `/api/internal/search`. |
| `brain_query_log` | `docs/AXIOM_COMPANY_BRAIN_AUDIT.md:191-193`, `docs/AXIOM_COMPANY_BRAIN_AUDIT.md:337` | No table/model/module found. |
| Agent preflight endpoint | `docs/AXIOM_COMPANY_BRAIN_AUDIT.md:238`, `docs/AXIOM_COMPANY_BRAIN_AUDIT.md:377` | No `/api/brain/agent-preflight` or `agent-preflight` implementation. |
| Approval queue UX / durable approvals | `DESIGN.md:636-640`, `DESIGN.md:1058-1060` | MCP service has in-memory `_approval_queue`; no durable table and no Studio approval queue UI found. |
| pgvector/Postgres-grade vector storage | Roadmap/brain audit future notes | No `pgvector`; current retrieval is SQLite/blob/local embeddings. |
| YC application material as product output | `docs/ROADMAP.md:346-360`, `docs/ROADMAP.md:382-407` | No generated YC app artifact or route; only roadmap text. |

## 10. Honest summary — one paragraph

Today AXIOM is a local FastAPI + SQLite + React/Three.js company-graph demo with 5,829 preloaded synthetic-ish entities, 26,536 edges, a working REST graph bootstrap, a WebSocket broadcaster, hybrid search, mocked/tested visual shell, a real encrypted key vault, backend passports, backend MCP tools, backend demo policy gates, backend hash-chain receipts, and backend watchdog rules. A user can run it locally, browse/search the graph, see governance snapshots, create/revoke passports, register agents/skills, and trigger backend watchdog/policy/receipt behavior in controlled paths. A user cannot rely on real source connectors, hosted production, auth/tenancy, Calibra uncertainty, real post-quantum receipt proof files, a durable approval workflow, frontend skill execution, frontend handling of denied/corrected agent-action events, or `/governance` as an actual receipt verification surface.
