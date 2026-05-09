# AXIOM AUDIT REPORT
Date: 2026-05-09
Auditor: Claude Code (read-only static + runtime audit)
HEAD commit: 2a220a1 (`phase 5.12.13: visual polish — primary spread, hub dimming, honest health card`)

---

## TL;DR

- **~35% real**: ingestion pipeline, SQLite persistence, organizer/keyword classifier, FastAPI + WebSocket pub/sub, Three.js brain rendering, ⌘K palette/search, cluster-health monitor. These actually run end-to-end.
- **~30% scaffolded-but-pretending-to-work**: governance, signing, receipts, "agent actions", warden insights, the entire `/api/sources` panel. Code exists, it emits events, but every byte of "decision", "signature", "merkle root", and "Slack/Linear/GitHub count" is randomly generated. There are zero real signatures, zero policies, zero connectors.
- **~10% dead code**: the entire `frontend/src/components/company-brain/` tree (~1,100 LOC) is orphaned — `App.tsx` imports nothing from it; only its own tests use it.
- **The 3 truths the owner needs**:
  1. The README's headline claim — *"signs every agent action with hybrid Ed25519 + ML-DSA-65 (FIPS 204) and enforces ALLOW / CORRECT / DENY / PAUSE"* — is false today. `src/axiom/sign/interfaces.py:23` is an abstract stub that raises `NotImplementedError`. No keypairs exist. Receipts are SHA-256 of `f"{action_id}:{decision}:{agent_name}:{index}"` (`src/axiom/govern/ledger.py:14`). The receipts table has **0 rows**.
  2. There are **no real source connectors**. `/api/sources` (`src/axiom/studio/sources.py:30`) returns hand-built rows where the count is computed `baseline + entity_count * (index+1)`. Slack/Linear/GitHub/Notion/Email are decorative strings.
  3. ~81% of edges in the live DB (11,216 of 13,805) are auto-generated `same_cluster_related` edges from `EdgeProposer` — they encode no real relationship, just "these two entities share a cluster."
- **The thing that would surprise the owner most**: the `/api/sources` panel that gives the live demo its credibility — the Slack/Linear/GitHub freshness, the rising counts — is not driven by anything. It's an arithmetic formula in a 47-line file. A YC reviewer who clicks "view source" or proxies a request will see this in under a minute.

---

## What's REAL (works end-to-end)

- **Ingestion → storage → broadcast pipeline.** `src/axiom/ingest/pipeline.py` reads `IngestEvent`s from a `Source`, writes via `crud.create_entity` / `crud.add_edge`, and publishes envelopes through `EventBroadcaster` (`src/axiom/ingest/broadcaster.py`). Verified live: `axiom.db` has 5,187 entities + 13,805 edges; `current_seq=2474` over the WS broadcaster.
- **Synthetic + LiveSynthetic sources.** `SyntheticSource` (`src/axiom/sources/synthetic.py`) loads `fixtures/synthetic_company.json` (100 entities, 170 edges). `LiveSyntheticSource` (`src/axiom/sources/live_synthetic.py:22`) seeds the DB then emits one event every ~8s using a Poisson interarrival (`sample_interarrival`, line 128). The generator (`src/axiom/sources/event_generators.py`, 389 lines) picks from canned title pools.
- **Hybrid keyword classifier.** `src/axiom/organize/classifier.py:78` does a real keyword count over 7 cluster vocabularies; argmax with deterministic tie-break (line 91). LLM fallback path exists (line 99) but is offline-safe and only fires on ambiguity. Live cluster distribution (5,187 entities) shows it actually ran: `billing_payments=1854`, `engineering_code=1296`, `incidents_ops=850`, `customer_support=750`, `decisions_policy=273`, `people_teams=121`, `growth_product=43`.
- **Organizer background loops.** `OrganizerAgent` (`src/axiom/organize/agent.py:50`) starts three asyncio tasks: classify (5s), centrality (30s), edge-proposal (15s). All three survive exceptions. `backfill_once` (line 177) runs at boot.
- **PageRank-based centrality scorer.** `src/axiom/organize/centrality.py` (125 lines) writes `composite_importance` to entities — non-zero importance values verified in DB.
- **FastAPI server + WebSocket replay.** `src/axiom/studio/server.py` exposes 7 routes (see API table below). `EventBroadcaster` keeps last 1,000 events with sequence numbers; `/ws/brain?since=N` replays from N forward (`broadcaster.py:42`). This is solid.
- **Frontend bootstrap.** `Brain.tsx:289-291` fetches `/api/entities`, `/api/edges`, `/api/cluster_health` from `127.0.0.1:8000` and seeds the Zustand store. `Brain.tsx:308` opens `ws://.../ws/brain` and calls `applyEvent` per envelope. Confirmed alive by `BrainSocket` on `frontend/src/lib/websocket.ts:60`.
- **Three.js scene.** `Brain.tsx` (837 LOC) renders hex-prism nodes, bracket cluster labels, particle conduits, idle-orbit camera. Rendering is real WebGL.
- **⌘K palette + entity search.** `CommandPalette.tsx` debounces 150ms and calls `/api/entities/search?q=...`. Backend (`src/axiom/api/search.py:39-83`) implements a real Levenshtein-on-title scorer with prefix/substring tiers + connection-count tiebreak. Falls back to client-side search if the request fails.
- **Cluster health monitor.** `ClusterHealthMonitor` snapshots ingest rates per cluster. The lifespan loop (`server.py:63`) emits `cluster_health_changed` events on status flips.
- **SQLAlchemy schema + migrations.** Two alembic revisions (`309b33ebec31_initial_schema`, `a1b2c3d4e5f6_add_cluster_id_and_importance`); 7 ORM tables; CRUD round-trip tested by `tests/test_storage*.py`. All 130 backend tests pass.
- **Tests.** Backend: `pytest` → 130 passed in 1.6s. Frontend: `vitest` → 270 passed, 5 failed (all 5 in dead code).

## What's SCAFFOLDED (exists but doesn't do what the name suggests)

- **`govern/agent_actions.py:35` `emit_agent_actions`**: an infinite loop that every 4–8s picks a random agent (`claude`/`cursor`/`gpt-5`), random cluster, random intent, then emits `agent_action`, `agent_action_evaluated`, and `receipt_added` envelopes. No real agent ever calls anything. The "decision" is a coin-flip in `SyntheticPolicyEvaluator.evaluate` (`src/axiom/govern/policy_evaluator.py:27`) — `if force_deny or self.rng.random() < self.deny_rate: return deny`. Reasons cycle through 4 hardcoded strings (`DENY_REASONS`, line 6). Policy IDs are `f"AEGIS-{(i % 9) + 1}"` (line 32).
- **`govern/ledger.py:7` `synthetic_receipt`**: returns `{receipt_id: sha256(f"{action_id}:{decision}:{agent_name}:{index}"), merkle_root: sha256("root:{index//10}:..."), ...}`. There is no signing, no Merkle tree, no key, no verifier. `Receipt.signature_ed25519_b64` and `signature_mldsa_b64` columns are never populated.
- **`govern/warden.py:40` `emit_warden_insights`**: every 30–90s, picks a random hardcoded message from `MESSAGES` (line 15 — 5 strings), a random severity, a random confidence in `[0.65, 0.95]`, and 3 hardcoded "recommended_actions" (line 35). Calls these "insights."
- **`/api/sources`** (`src/axiom/studio/sources.py:30`): the headline "data source freshness" panel. Hand-built `SOURCE_BASELINES` (line 20) with formula `count = baseline + entity_count * (index+1)`. Slack/Linear/GitHub/Notion/Email/Meetings are strings. `live: bool` is hardcoded per index. **There are no connectors anywhere in `src/axiom/`** — `grep -rn "slack\|github\|linear\|notion" src/axiom/sources/` finds only fixture title strings.
- **`sign/interfaces.py`**: abstract `Signer.sign` and `verify` raise `NotImplementedError("...stubbed; lands in Phase 10")`. No implementation file exists in `src/axiom/sign/`. Same shape for `policy/interfaces.py` (Phase 9), `skills/interfaces.py` (Phase 8), `mcp/interfaces.py` (Phase 6) — all abstract, no concrete subclass anywhere.
- **`EdgeProposer`** (`src/axiom/organize/edge_proposer.py:22`): runs every 15s and creates `same_cluster_related` edges between any two unconnected entities in the same cluster. This is responsible for **11,216 of 13,805 edges (81%)** in the DB. They look like real relationships in the UI but encode only "these were both classified into bucket X."
- **`EntityInspector` "Trust & Governance" panel** (`frontend/src/components/EntityInspector.tsx:156-169`): hardcoded `Policy Status: Compliant`, `Signed Receipt: Verified`, plus a fake Merkle root derived from the entity ID (`"0x" + entity.id.replace(/[^\da-f]/gi, "").padEnd(12, "0").slice(0, 12)` — line 99). Copy button copies this fake root.
- **`EntityInspector` tabs Connections/Lineage/Activity** (line 134): every non-Overview tab renders the literal string "This tab is reserved for the next interaction pass." Three of four tabs are placeholder.
- **`QueryBar` send button**: dispatches `axiom:traverse-clusters` (line 18) and `axiom:open-palette` (line 15). The first event has no listener wired to a real query path; the second just opens the ⌘K palette. There is no LLM Q&A and no `/api/query` endpoint. The "Ask the Company Brain anything..." input is search-only.
- **`BrainHealthCard` sparkline** (`frontend/src/components/BrainHealthCard.tsx:54`): the first 36 data points are a hardcoded array literal `[89, 91, 90, 92, 91, ...]`. The card is honest about Health % (computed from `clusterHealth`), but the historical chart is fake until enough seconds pass to overwrite it.

## What's DEAD (orphaned/unused/never wired)

- **Entire `frontend/src/components/company-brain/` tree** (~1,100 LOC): `CompanyBrainPage.tsx` (419), `CompanyBrainGraph.tsx` (154), `HexConstellation.tsx` (177), `HubNode.tsx` (72), `ClusterNode.tsx` (83), `Conduit.tsx` (83), `companyBrainData.ts`, `companyBrainTypes.ts`. `App.tsx` does not import any of these. Only its own `__tests__/` reference it. **5 failing tests live here** — the tests are testing scrolling/cluster-click flows in this dead path.
- **`frontend/src/components/PhaseStubApp.tsx`** (4 lines): unreferenced.
- **`frontend/src/components/BrainCanvas.tsx`** (4 lines): unreferenced.
- **`frontend/src/components/HUD.tsx`** (154 LOC): not imported by `App.tsx`. Unreferenced.
- **`receipts`, `actions`, `skills`, `sources` DB tables**: all have **0 rows**. The agent_actions/warden loops emit broadcast envelopes but never persist to these tables. The ORM models exist, no code path writes to them.
- **`src/axiom/cli.py`** (74 lines): worth checking if anything uses it; not imported by the studio server.

## What's MISLEADING (README/UI says something the code doesn't deliver)

- **README**: *"signs every agent action with hybrid Ed25519 + ML-DSA-65 (FIPS 204)"* → there is no signing. `src/axiom/sign/` contains only an abstract stub. The `cryptography` library is not even imported. (`grep -rn "ed25519\|nacl\|cryptography\|ml-dsa\|ml_dsa" src/axiom/` returns zero hits.)
- **README**: *"enforces a three-mode policy: ALLOW / CORRECT / DENY (plus PAUSE when uncertain)"* → `SyntheticPolicyEvaluator` only ever returns `"allow"` or `"deny"`. `"correct"` and `"pause"` are never produced. The "policy" is `random.random() < 0.15`.
- **README**: *"Hosted demo: `https://axiomctrl.com`"* → `curl -I` returns **HTTP/2 522** (Cloudflare can't reach origin). The demo is not live.
- **README**: *"Phase 5.7 hybrid cluster classifier's LLM fallback (Anthropic Haiku)"* → the path exists but the model ID at `classifier.py:38` is `"claude-haiku-4-5-20251001"` — verify this is still a valid public model name when you submit; if not, mention something safer or remove the claim.
- **`StatusFooter` tabs** (`Graph / Flow / Governance / Timeline / Search / Receipts / Agent Console`): plain `<button>` elements with no `onClick` (`StatusFooter.tsx:12`). They are pure decoration.
- **`NavRail` items** (`Brain / Explore / Agents / Insights / Governance / Settings / Account`): no `onClick`, no router (`NavRail.tsx:38`). All decorative.
- **`/api/sources` "freshness" panel**: every "Xm ago" / "1h ago" timestamp comes from `now - timedelta(minutes=(index+1)*2)` (`studio/sources.py:37`). Always identical, never reflects ingest reality.
- **README phase claims**: README still says "Phase 0 ✅ / Phase 1 ✅ / Phase 2 ⏳ / Phases 3–15 ⏳" — but commit `2a220a1` is "phase 5.12.13". The README has not been updated since Phase 1; it's dramatically out of sync with what's actually built.

## Subsystem-by-subsystem detail

### Ingestion
Real. `IngestPipeline._handle` (`src/axiom/ingest/pipeline.py:32`) handles `entity_added` and `edge_added` event types and persists them. Other event types fall through to a no-op broadcast (line 92). Nick→ID resolution lives in-memory in `self._nick_to_id`. **Risk**: in-memory map means edges that arrive before their endpoints (or after a restart) silently drop on lines 70-71.

### Classification
Real (keyword tier). `HybridClassifier.classify` (`classifier.py:61`) does keyword scoring; LLM fallback is plumbed but offline by default (no `ANTHROPIC_API_KEY` → `_resolve_client` returns None → falls back to argmax/default cluster). 7 backend clusters; reframed to 8+ super-clusters in `frontend/src/lib/cluster-reframe.ts:21`.

### Governance
Scaffold theatre. Three async loops (`agent_actions`, `warden`, plus the `cluster_health` loop) emit envelopes on a timer. Nothing inspects or gates real activity. The "policy" is randomness. The "receipts" are SHA-256 of metadata strings. The `Action` and `Receipt` SQL tables are never written to.

### API
| Path | Method | Behavior | Used by frontend |
|---|---|---|---|
| `/api/health` | GET | `{status, current_seq, live, events_emitted}` — real | Not currently consumed by `App.tsx`/`Brain.tsx`; CompanyBrainPage (dead) does poll it |
| `/api/entities` | GET | Full table dump (5,187 rows) | `Brain.tsx:289` |
| `/api/edges` | GET | Full table dump (13,805 rows) | `Brain.tsx:290` |
| `/api/cluster_health` | GET | Real per-cluster snapshot from `ClusterHealthMonitor` | `Brain.tsx:291` |
| `/api/sources` | GET | **Fully synthetic** Slack/Linear/etc | not currently rendered (no chrome calls it) |
| `/api/entities/search` | GET | Real Levenshtein-based ranking | `CommandPalette.tsx:14` |
| `/ws/brain` | WS | Real pub/sub w/ replay | `Brain.tsx:308` |

No `/api/query`, no LLM endpoint, no skills endpoint, no auth.

### WebSocket
Real transport. Event flow: classifier loops + agent_actions loop + warden loop + cluster_health loop + ingest pipeline → `EventBroadcaster.publish` → in-memory deque (1,000 cap) → all subscriber queues. Replay via `?since=N` works. **The events themselves are mostly synthetic** — agent_action/agent_action_evaluated/receipt_added every ~5s, insight_flagged every 30–90s, all from RNG.

### Persistence
Real. `axiom.db` is 11.9 MB, has 7 tables, alembic up to head. CRUD layer (`src/axiom/storage/crud.py`, 157 LOC) is straightforward SQLAlchemy 2.0. Indexes on (type, created_at), (source_id, relationship), etc. Receipts/actions/skills tables are present but unused.

### Skills/MCP
Does not exist. `src/axiom/skills/` and `src/axiom/mcp/` contain only `interfaces.py` with abstract methods raising `NotImplementedError`. No MCP server is started; no skill is emitted; the skills table has 0 rows. The README's "Skills exposed via MCP" is a Phase 6/8 promise, not a present capability.

### Frontend rendering
Real and the strongest part of the codebase. `Brain.tsx` (837 LOC) renders hex-prism node geometry, bracket cluster labels via CSS2DRenderer, particle conduits between hubs, idle orbit, post-processing bloom, FPS counter, camera-fly-to. Bootstraps from real `/api/entities` + `/api/edges`. Bracket labels driven by entity counts per super-cluster; intra-cluster web lines computed from real edge data.

### Frontend chrome
| Component | Status | Notes |
|---|---|---|
| `NavRail` | **DECORATIVE** | No `onClick`/router; visual only |
| `TopHeader` | DECORATIVE | 17-line static SVG + LIVE pill (which doesn't reflect ws status) |
| `BrainHealthCard` | **FUNCTIONAL** for Entities/Relationships/Events-min/Health (real); sparkline first 36 points hardcoded |
| `QueryBar` | **STUB** | Triggers `axiom:open-palette`/`axiom:traverse-clusters`; no real query backend |
| `EdgeLegend` | DECORATIVE | 21-line static color swatches |
| `EntityInspector` Overview | FUNCTIONAL (mostly — Trust&Gov sub-section is fake) |
| `EntityInspector` Connections/Lineage/Activity | **STUB** | Renders placeholder string |
| `StatusFooter` tabs | **DECORATIVE** | No handlers |
| `CommandPalette` | **FUNCTIONAL** | Real backend search + keyboard nav + select/fly-to |

### Tests
- Backend: `pytest -q` → **130 passed**. Mostly real behavior tests (synthetic source iteration, CRUD round-trip, classifier scoring, organizer loops, edge-proposer dedup, cluster-health transitions, websocket replay).
- Frontend: `vitest run` → **270 passed, 5 failed**. All 5 failures are in `frontend/src/components/company-brain/__tests__/CompanyBrainGraph.interaction.test.tsx`, testing UI flows in the orphaned `company-brain/` tree (cluster-click → entity-click navigation that times out waiting for `findByLabelText(/Systems cluster,/i)`). **Recommendation: delete the entire `company-brain/` directory and its tests** — they don't test the live app.
- The remaining 270 frontend tests cover real components (cluster reframe, hex layout, palette, brain store, websocket, FPS, etc.) and are non-trivial.

### Deployment
- No `Dockerfile`, no `docker-compose.yml`, no Render/Fly/Vercel config in repo root.
- `.github/workflows/ci.yml` exists (not inspected; presumably runs tests).
- `axiomctrl.com` returns **HTTP 522** — origin unreachable. Not a working hosted demo.
- Hardcoded `http://127.0.0.1:8000` in `Brain.tsx:289-291` and `CompanyBrainPage.tsx:62` — would need to be `import.meta.env.VITE_API_BASE` (or similar) before any non-localhost deploy.
- No secrets in repo (`.env.example` only references `ANTHROPIC_API_KEY` and `DATABASE_URL`; verified no API keys leak via code search).

---

## YC submission risk assessment

A reviewer who clones, runs `pip install -e . && uvicorn axiom.studio.server:app --factory` (well, `create_app()`) plus `cd frontend && npm install && npm run dev` and clicks around will see:

- A **genuinely beautiful** Three.js brain rendering 5,000+ real nodes with real cluster classification, real WebSocket event flow, and a working ⌘K search. This is impressive and not fake.
- An "agent activity" feed scrolling random allow/deny decisions every 5s, each with a SHA-256 "receipt." If they read `govern/ledger.py` (25 lines) they will see in 30 seconds it's `hashlib.sha256(f"{action_id}:{decision}:..."`. That is the credibility cliff.
- A `/api/sources` "Slack 6,434 / Linear 10,686 / GitHub 15,650" panel (currently not rendered in chrome but reachable via curl) where the numbers are `baseline + entity_count * (index+1)`. If they hit `/api/sources` directly they'll see this immediately.
- A README that says "signs every agent action with Ed25519 + ML-DSA-65" against a `src/axiom/sign/` directory containing one file with `raise NotImplementedError`.

**The 3 specific things a YC reviewer could call out as "this doesn't actually work":**
1. **"Where is the signing code?"** — there isn't any. The whole governance pillar is RNG.
2. **"Where are the connectors?"** — there are none. `/api/sources` is a constant table.
3. **"What happens when I click Governance / Receipts / Agents in the nav?"** — nothing. They are static SVGs.

**Recommendation: polish first, don't ship as-is, don't rebuild.** The visual + ingest + classifier + WebSocket spine is legitimate work and would survive a 30-minute YC look. The fragile parts are (a) the README's overclaiming, (b) the `/api/sources` panel, (c) the `EntityInspector` Trust & Governance fake Merkle root, and (d) the dead `company-brain/` tree shipping with failing tests. All four are 1-day or less to fix without lying.

---

## Recommended next steps (prioritized for time-to-YC)

### 1-hour fixes (quick credibility wins)
- **Rewrite the README** to match reality. Replace "signs every agent action with Ed25519 + ML-DSA-65" with "Phase-roadmapped: cryptographic receipts (Phase 10)." Replace "ALLOW / CORRECT / DENY / PAUSE" with what's real today. Update the phase checklist (Phase 5.12 is current, not Phase 1).
- **Delete `frontend/src/components/company-brain/` and its `__tests__`.** This removes the 5 failing tests and ~1,100 LOC of dead code in one stroke. Confirm no imports first (`grep -rn "company-brain" frontend/src` outside the directory itself).
- **Either remove `axiomctrl.com` from the README, or stand up a placeholder.** A 522 origin is worse than no link.
- **Rename `synthetic_receipt`/`synthetic_action_payload` to make their nature explicit** (e.g., `demo_receipt`, `demo_action`) and add a `demo: true` flag in the envelope payload. This protects you from the "you lied" framing.
- **Hide or label `/api/sources`.** Either remove the route until you have a real connector, or have it return `{ "demo_data": true, ... }` with the sources behind a feature flag.

### 1-day fixes (real product progress)
- **Real Ed25519 signing on receipts.** `cryptography.hazmat.primitives.asymmetric.ed25519` + a dev keypair stored at `~/.axiom/dev_signing_key.pem`. Sign `{action_id, cluster_id, decision, timestamp}` in `synthetic_receipt`. Store `signature_ed25519_b64` in the `receipts` table (which is currently empty). This converts the entire receipts story from theatre to "v0 with hybrid PQ deferred to Phase 10." Realistic in <1 day.
- **Wire the `EntityInspector` tabs (Connections at minimum).** You already compute `connected` (line 50). Render the same list under the Connections tab. Lineage = `created_at` walk. Activity = events from the broadcaster. Removes the "reserved for next pass" string from 3 of 4 tabs.
- **Make `QueryBar` do something honest**: even just routing to `CommandPalette`'s search and showing top results in a dedicated overlay. The current input that does nothing is the worst possible state.
- **Replace `studio/sources.py` with a query against actual `Entity.source_id` groupings.** Even if the sources are still synthetic, the count should be a real `GROUP BY source_id` against the DB, not arithmetic.
- **Persist `agent_actions` to the `actions` table and `receipts` to the `receipts` table.** These tables exist; nothing writes to them. One write per loop iteration in `govern/agent_actions.py:46` is 5 lines.

### 1-week fixes (substantial new capability)
- **One real connector.** Slack with a single channel + Bot token, or GitHub with a single repo + PAT. Replace `LiveSyntheticSource` with `SlackSource` for one entity stream. Even 50 real Slack messages classified into clusters is the difference between "beautiful demo" and "actually a company brain."
- **Real `PolicyEngine` with at least one rule** (e.g., "agent X cannot write entities in cluster billing_payments without a referenced decision"). Implements `policy/interfaces.py`. Gate `IngestPipeline._handle` through it. Three real rules in YAML in `policies/` is enough.
- **MCP server with 1–3 real skills** (lookup_entity, search_brain, list_recent_decisions). `mcp/interfaces.py` is already typed; `mcp.server` Python SDK ships in <300 LOC.

### Things to NOT do (scope traps)
- Don't try to ship ML-DSA-65 / FIPS 204 hybrid signing before YC. Use Ed25519 alone and tell the truth about the roadmap. PQ signing libraries in Python are immature and will eat a week.
- Don't try to wire all 7 nav items. Pick one (Governance) and route it; mark the rest as "Coming in Phase 6."
- Don't add a Calibra integration before YC. The README says it lands in Phase 7. Keep it that way.
- Don't refactor `Brain.tsx` (837 LOC). It works. Touch only the chrome around it.
- Don't rebuild the dead `company-brain/` tree. Delete it.
