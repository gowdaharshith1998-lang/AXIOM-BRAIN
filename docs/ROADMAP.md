# AXIOM — Full Build Roadmap (Scratch Rebuild)

> **Date:** 2026-05-05
> **Owner:** Hg, AXIOM Control Systems Inc. (Delaware C-Corp)
> **Co-founder (equity established, vesting unsigned):** Gagan
> **Status:** Scratch rebuild greenlit. Foundational dispatch next.
> **Source of truth:** this file. Supersedes `OMNIX_AXIOM_CALIBRA_ROADMAP_2026-05-05.md`.

---

## Naming convention (locked, do not violate)

- **AXIOM** — the product. Used in user-facing UI, CLI binary, Python package name, MCP server identity, marketing, pitch, application copy, video, anywhere external.
- **AXIOM** — also the runtime governance layer inside the product (ALLOW/CORRECT/DENY policy engine, signing, Merkle log). The name doubles intentionally — the brand signals "signed, governed, verifiable" everywhere it appears.
- **AXIOM-BRAIN** — the GitHub repo name only. `gowdaharshith1998-lang/AXIOM-BRAIN`. Never user-facing.
- **Calibra** — separate library, imported as external Python package from `~/brain-experiments/`. Ships its own roadmap. Provides Bayesian confidence calibration.
- **OMNIX** — retired. Old product name. Archived to `~/omnix-legacy/`. Does not appear in new code, new docs, or new pitch material.

Architecture sentence for pitch and docs:
> "AXIOM is the company brain. Inside AXIOM, the governance subsystem (also called AXIOM) signs every agent action with post-quantum cryptography and enforces ALLOW/CORRECT/DENY policy on every read and write. Calibra provides Bayesian confidence calibration on every fact in the brain."

---

## North star

A multi-source visual company brain. One repo, one product, hosted production from day 1.

- **Pulls knowledge** from external systems via connectors (Linear first, then Slack, Gmail, Drive, GitHub)
- **Structures it** as 7 universal entity types (code, people, decision, thread, ticket, document, process) plus typed relationships
- **Renders it** as a 3D volumetric brain in the browser at 60+ FPS using Three.js + WebGPU + three-nebula particles
- **Exposes it** via MCP tools so AI agents can query the brain structurally (research-backed 20–34% accuracy gain over flat-text RAG)
- **Governs every agent action** through the AXIOM policy engine with three response modes: ALLOW (sign and execute), CORRECT (return guidance, agent retries), DENY (refuse and queue for human approval). Every action post-quantum signed (ML-DSA-65) and Merkle-anchored (RFC 6962).
- **Calibrates every fact** through Calibra (KNOW / UNCERTAIN / UNKNOWN dispositions; confidence + surprise + free-energy scalars per belief). Uncertain beliefs gate agent action with a fourth response mode: PAUSE (gather more evidence first).
- **Emits executable skill files** (`.md`) that agents load via MCP. Each skill load is signed. Skills compile from process entities the brain identifies across sources.

Two interfaces, one substrate: agents query through MCP (graph data), humans supervise through the visual brain (anomaly detection, approval queue, signed receipt trail).

---

## SECTION 1 — FOUNDATIONAL DECISIONS (locked)

### F1 — Build approach
**Scratch build with established libraries for crypto correctness only.**

- Product code (schema, ingest, MCP server, studio shell, skills emitter, policy engine, sign-on-action wrapper, connectors): written fresh, no vendoring from OMNIX.
- PQ crypto: use `pqcrypto` Python package (NIST FIPS 204 reference implementation, audited). Do NOT roll our own ML-DSA-65.
- Ed25519: use `cryptography` Python package. Do NOT roll our own.
- RFC 6962 Merkle: write fresh (~100 lines, well-documented standard, low risk).
- Bayesian math: import Calibra as external package. Do NOT vendor or re-derive.
- 3D rendering: write fresh in Three.js + WebGPU + three-nebula. Do NOT vendor the 2D PixiJS renderer from OMNIX.

### F2 — Repo
- GitHub: `gowdaharshith1998-lang/AXIOM-BRAIN` (private, already created)
- Local: `~/AXIOM-BRAIN/`
- Old repos archived: `~/omnix/` → `~/omnix-legacy/`, `~/AXIOM-V2/` → `~/axiom-v2-legacy/`. Kept on disk for reference. Lose nothing.
- Calibra stays at `~/brain-experiments/` for ongoing Layer 1 development; AXIOM-BRAIN imports it as a package.

### F3 — Stack
- **Python:** 3.13+ (`pqcrypto`, `cryptography`, `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `pytest`, `httpx`, Calibra)
- **Frontend:** React 18 + Vite + TypeScript + Tailwind + Zustand + Three.js + WebGPU + three-nebula + 3d-force-graph
- **Storage:** SQLite + WAL for the brain (single-tenant). Postgres deferred to multi-tenant slice.
- **Wire protocol:** WebSocket for live brain mutation. JSON message envelopes.
- **MCP:** Single server exposing 15-20 universal tools (brain query, traverse, get entity, list skills, attest skill load, sign action, verify receipt, etc.)
- **Hosted production:** Render.com or Fly.io for backend, Vercel or Cloudflare Pages for frontend, custom domain `axiom.brain` or similar (decide before Phase 11).
- **Secrets:** GitHub Actions secrets for CI; production secrets in hosting platform's secret manager.
- **OAuth callbacks:** production URLs from Phase 11 onward; localhost callbacks for dev.

### F4 — Demo target
**Hosted production from day 1.** Public URL anyone can hit. Send YC partners a link, not a video.

Implications:
- Deployment infra is part of the build (Phase 11), not an afterthought
- OAuth callbacks point at production URLs
- Basic auth gate or signup flow before the demo brain is visible (don't expose connector credentials publicly)
- HTTPS and proper certificate setup
- Optional: a "demo workspace" pre-populated with synthetic data anyone can browse without auth, then a "connect your own" flow for hands-on

### F5 — First connector
**Linear.** Reasons:
- Cleanest OAuth flow of the candidates (single token type, no workspace-vs-user-install distinction, well-documented callback)
- Tickets map directly to the universal Ticket entity
- Webhooks reliable
- API rate limits generous

Slack, Gmail, Drive, GitHub follow in Phase 12+ once Linear validates the connector substrate.

### F6 — Demo workspace data
**Synthetic data fixture for offline development, real Linear workspace for hosted production.**

- Phase 3-9 use a synthetic fixture file (~100 fake entities spanning all 7 types) so OAuth doesn't block downstream phases
- Phase 11 (hosted production) wires the real Linear OAuth flow
- Phase 12 onward adds additional real connectors

### F7 — Calibra integration timing
**Calibra Layer 0 capabilities work day 1** (12 MCP tools shipping at `python -m brain.mcp.server`, 448 tests green). AXIOM-BRAIN imports Calibra and calls `observe()` / `query()` / `recall()` from line 1.

Calibra Layer 1 (4-8 weeks per Calibra MASTER_ROADMAP.md) ships PAUSE response mode + advanced features. AXIOM-BRAIN consumes Layer 1 capabilities as Calibra ships them — no AXIOM-BRAIN code change needed beyond importing the new version.

### F8 — YC application timing
Drafted in parallel with Phase 8+ (skills emitter and beyond). Application doesn't need final code; needs working hosted demo by submission. Drafting in parallel saves a calendar week.

---

## SECTION 2 — BUILD SEQUENCE (15 phases)

Each phase = one Cursor dispatch. Multiphase only when natural recon + phase structure (slice-21 pattern). Branches stack: each off the previous phase tip; main only updated after a logical block ships.

### Phase 0 — Schema + interface design (HALT for review)
**Goal:** Lay out everything before any code. Output a design doc dispatcher reviews before Phase 1 starts.

- Read Blomfield's Company Brain RFS phrase by phrase (verbatim text now in roadmap appendix below)
- Read Diana Hu's "AI Operating System for Companies" RFS phrase by phrase
- Define entity schema: 7 types (code, people, decision, thread, ticket, document, process), required fields, optional fields, metadata JSON contract
- Define edge schema: typed relationships, free-text relationship column, source attribution
- Define receipt schema: action receipts, ingest receipts, skill-load receipts, governance receipts (CORRECT signals, DENY signals)
- Define `Source` ABC: `discover()`, `ingest()`, `watch()`, `metadata()`, `disconnect()`
- Define MCP tool surface: ~15-20 tools, exact signatures, request/response shapes
- Define policy YAML schema: `allow` / `correct` (with `guidance`) / `deny` clauses, retry budget, drift thresholds
- Define skills emitter output: SKILL.md schema with front-matter (id, version, scope, inputs, outputs, side_effects, requires_approval, calibra_threshold) and markdown body
- Define WebSocket message types
- Define hosting/deployment topology
- Output: `DESIGN.md` in repo root

**HALT for review.** Dispatcher confirms design before Phase 1.

**Branch:** `phase-0-design`

### Phase 1 — Repo skeleton + dependencies
**Goal:** Empty repo becomes runnable scaffolding. All interfaces stubbed, all stubs tested.

- Initialize `~/AXIOM-BRAIN/`, push to GitHub
- `pyproject.toml` with deps: `pqcrypto`, `cryptography`, `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `pytest`, `httpx`, `pytest-asyncio`, `calibra` (path import from `~/brain-experiments/`), `pydantic`, `python-dotenv`
- `package.json` for frontend: React, Vite, TypeScript, Tailwind, Zustand, Three.js, three-nebula, 3d-force-graph, vitest
- Directory structure: `src/axiom/{schema,ingest,mcp,studio,skills,policy,sign,sources}/`, `frontend/src/{components,lib,state,styles}/`, `tests/`
- All core ABCs/interfaces stubbed with type hints
- All stub tests pass (assert interface signatures match spec)
- CI: GitHub Actions running pytest + vitest on push
- README pointing at hosted demo URL (placeholder until Phase 11)
- License: MIT for OSS layer (decide commercial line later — see Open Decision OD3)

**Branch:** `phase-1-skeleton`

### Phase 2 — Schema + storage
**Goal:** SQLite schema with universal entity types, migrations, CRUD layer, tests.

- Alembic migrations for `entities`, `edges`, `receipts`, `actions`, `sources`, `skills` tables
- Free-text type columns on entities and edges (no migration needed when adding entity types later)
- Pydantic models matching schema
- CRUD layer with `create_entity`, `get_entity`, `update_entity`, `delete_entity`, `query_entities`, `list_neighbors`, `add_edge`, `remove_edge`
- Tests: round-trip CRUD, type-tagging, JSON metadata, neighbor queries, edge cases
- 7 entity types are treated equally — no code-as-default

**Branch:** `phase-2-schema`

### Phase 3 — Synthetic data fixture + ingest pipeline
**Goal:** Brain populates from a synthetic fixture without needing real OAuth. Unblocks downstream phases.

- `fixtures/synthetic_company.json`: ~100 entities spanning all 7 types
  - 5 People (with display names, roles)
  - 3 Channels worth of Threads (~30 messages threaded into 8 conversations)
  - 12 Tickets in various states
  - 8 Documents
  - 4 Decisions
  - 3 Processes
  - 2 Code modules (yes, one of seven — universal applicability requires code as one option)
  - Cross-source edges (Decision_X relates to Thread_Y relates to Ticket_Z)
- Generic `Source` implementation: `SyntheticSource` reads fixture, emits ingest events
- Ingest pipeline: `Source.ingest()` → entity normalization → schema CRUD → WebSocket broadcast
- Tests: ingest fixture, assert 100 entities exist, assert edges connect correctly

**Branch:** `phase-3-synthetic-ingest`

### Phase 4 — 3D visual brain (fresh)
**Goal:** Render the entity graph as a 3D volumetric brain in the browser.

- React + Three.js + WebGPU renderer
- 3d-force-graph for force-directed layout
- Entity-palette tinting (7 colors + fallback)
- Brain envelope distribution (similar to slice-20 pattern but 3D — entities cluster within an organic shape, not a hex plane)
- 60+ FPS target on AMD Radeon 840M (founder's hardware floor)
- Camera controls: orbit, zoom, click-to-focus
- WebSocket subscription for live mutation
- HUD: entity count, FPS counter, breadcrumb
- TSL post-processing pipeline: bloom, ACES tone mapping, optional DOF
- Tests: renderer initializes, FPS stays >55, entities render with correct color, click-to-select fires event

**Branch:** `phase-4-3d-brain`

### Phase 5 — three-nebula particle effects (live agent activity)
**Goal:** Particles render live agent activity through the brain. Not just decoration — particles ARE the agent activity, visualized.

- Install three-nebula
- Particle behaviors:
  - **Agent traversal:** when an agent reads an entity via MCP, particles flow along edges from agent's last-read entity to current entity
  - **Signing burst:** when AXIOM signs an action, brief particle burst at the entity location, color-coded by signing scheme (Ed25519 = green, ML-DSA-65 = blue, hybrid = teal)
  - **Ingest stream:** when a connector ingests new data, particles stream from a source-tagged screen edge into the new entity location
  - **Confidence decay:** when Calibra reduces confidence on a fact (volatility decay), particles dissipate slowly from that entity
  - **Refusal pattern:** when AXIOM DENIES an action, red particle burst with refusal pattern at the attempted entity
  - **CORRECT signal:** when AXIOM returns CORRECT, amber particle wave from blocked entity to suggested entity (visual guidance)
- Tests: particles emit on synthetic agent events, FPS stays >55 with all particle systems active

**Branch:** `phase-5-particles`

### Phase 6 — MCP server (universal tools, no code-bias)
**Goal:** AI agents can query the brain through MCP. ~15-20 tools exposing brain query, skills, receipts, governance.

- `axiom_query_brain(filter)` — query entities by type, source, metadata
- `axiom_get_entity(id)` — full entity payload + neighbors
- `axiom_traverse(from_id, edge_types, max_depth)` — path traversal
- `axiom_list_sources()` — connected sources, status, last sync
- `axiom_list_skills()` — emitted skills (Phase 8 ships skills; tool exists from Phase 6)
- `axiom_load_skill(skill_id)` — return SKILL.md content + sign attestation
- `axiom_attest_skill_load(skill_id, agent_id)` — record signed attestation
- `axiom_get_receipts(filter)` — list receipts with verify status
- `axiom_verify_receipt(receipt_id)` — run live verification
- `axiom_check_policy(action_payload)` — pre-flight policy check before attempting
- `axiom_record_action(action_payload, result)` — sign + Merkle-anchor an action
- `axiom_get_calibra_confidence(entity_id)` — read confidence from Calibra (Phase 7 wires this)
- `axiom_pause_for_evidence(belief_id, agent_id)` — explicit PAUSE acknowledgment
- `axiom_request_human_approval(action_id, reason)` — escalation path
- All tools sign their inputs/outputs with the action wrapper from Phase 9
- Tests: each tool's request/response shape, error handling, concurrent calls

**Branch:** `phase-6-mcp`

### Phase 7 — Calibra integration
**Goal:** Calibra is wired into ingest and query paths. Every fact has a confidence score visible in the brain.

- AXIOM-BRAIN imports `calibra` from local path
- Ingest pipeline calls `calibra.observe(belief, evidence)` for each entity created/modified
- Query pipeline reads `calibra.query(belief_id)` to enrich entity payloads with `metadata.calibra_state` (KNOW/UNCERTAIN/UNKNOWN), `metadata.confidence`, `metadata.surprise`, `metadata.free_energy`
- 3D renderer reads `metadata.confidence` for entity opacity (low confidence = ghostly translucent, high confidence = solid)
- MCP `axiom_get_calibra_confidence` returns live values
- Skill execution checks belief confidence before acting (PAUSE response mode if UNCERTAIN; documented in policy in Phase 9)
- Tests: synthetic ingest → confidence appears on entities; query reflects updated confidence; renderer shows opacity changes

**Branch:** `phase-7-calibra-integration`

### Phase 8 — Skills emitter
**Goal:** AXIOM emits SKILL.md files. Each skill is signed. Agents load skills via MCP and execute them in their own runtime.

- Walk Process entities in the brain
- For each Process, identify the steps it implies (cross-reference Threads, Decisions, Tickets, Documents that mention it)
- Emit SKILL.md with front-matter (id, version, scope, inputs, outputs, side_effects, requires_approval, calibra_threshold) and markdown body
- Each emitted skill signed (Ed25519 + ML-DSA-65 hybrid)
- Skills written to `~/.axiom/skills/<skill_id>.md` plus signature sidecar `<skill_id>.sig`
- New SKILLS panel in studio (or skills surface within an entity inspector if Process is selected)
- MCP `axiom_list_skills` and `axiom_load_skill` already wired in Phase 6 — Phase 8 fills the data
- Tests: synthetic Process entity → SKILL.md emitted → signature verifies → MCP returns it correctly

**Branch:** `phase-8-skills-emitter`

### Phase 9 — Policy engine: ALLOW / CORRECT / DENY (the YC differentiator)
**Goal:** Three-mode policy enforcement on every agent action. CORRECT mode is the closed-loop differentiator no other governance vendor ships.

- Policy YAML schema (per Phase 0 design): `allow` clauses, `correct` clauses with `guidance` + `allowed_alternative_tool` + `allowed_alternative_params`, `deny` clauses
- Default policy file: `policies/intelligent.yaml` shipping with sensible defaults
- Policy engine evaluates incoming action payload against policy
- Three response shapes:
  - ALLOW → action proceeds to execution + signing
  - CORRECT → return signed corrective signal to agent (action does NOT execute); agent sees guidance, retries with corrected approach
  - DENY → refuse, sign refusal, queue for human approval
- Retry budget tracking per `task_id`: 3 CORRECTs in same task = auto-DENY with `escalate_to: human_approval_queue`
- Drift detection: 2 CORRECTs in adjacent state-space (cosine similarity > 0.85) = drift warning
- AGENT panel in studio: distinguish ALLOW (green ring), CORRECT (amber pulse), DENY (red, queued)
- Approval queue: humans review queued DENY actions, approve/reject (their decisions also signed)
- Tests: synthetic action payloads against synthetic policies, all three response modes, retry budget enforcement, drift detection, escalation flow

**Branch:** `phase-9-policy-engine`

### Phase 10 — Sign-on-action wrapper
**Goal:** Every MCP tool call wrapped with signing. Reads, writes, traversals, skill loads, refusals — all signed and Merkle-anchored.

- Wrapper around all 15+ MCP tools from Phase 6
- Action payload canonicalized: `(agent_id, tool, params, timestamp, result_hash, before_hash?, after_hash?)`
- Hybrid signing: Ed25519 (fast) + ML-DSA-65 (post-quantum) on every action
- Append to Merkle log → leaf index returned in receipt
- Receipt stored at `~/.axiom/receipts/actions/<action_id>.json`
- WebSocket emits `action_signed` event → AGENT and HISTORY panels update
- Verify endpoint: `axiom_verify_receipt(action_id)` returns verified/unverified/error
- Tests: synthetic actions sign correctly, signatures verify, Merkle leaves anchor, receipts persist, verification works

**Branch:** `phase-10-sign-on-action`

### Phase 11 — Hosted production deployment
**Goal:** AXIOM runs at a public HTTPS URL. Partners click a link, not a video.

- Backend hosting: Render.com or Fly.io (decide based on cost/perf — recommend Fly.io for global edge, Render for simpler setup)
- Frontend hosting: Vercel or Cloudflare Pages
- Custom domain: TBD (decide before this phase — `axiom.work`? `getaxiom.com`? `axiom.brain`? Something else? See Open Decision OD1)
- HTTPS with automatic certificate (Let's Encrypt via hosting platform)
- Environment variables and secrets managed in hosting platform
- Database: SQLite WAL mode (single-tenant production OK; multi-tenant via Postgres in OD2)
- WebSocket support verified end-to-end through hosting platform's proxy
- Basic auth gate before connector setup (don't expose OAuth flow publicly)
- "Demo brain" preloaded with synthetic data, browsable without auth (lets partners see the visual brain immediately)
- "Connect your own" flow behind auth (real OAuth callbacks)
- Tests: smoke tests against production URL run in CI

**Branch:** `phase-11-hosted-production`

### Phase 12 — Linear connector (first real connector)
**Goal:** Real Linear OAuth flow → real Linear data ingested → brain populates with the user's actual workspace.

- Linear OAuth app registered, callback URL pointing at production
- OAuth flow in studio: "Connect Linear" button → Linear authorization → token stored encrypted
- Linear API client (use `linear-python` if mature, else write thin wrapper around their GraphQL API)
- Entity normalization: Linear ticket → Ticket entity, assignee → Person entity, project → Process entity, comments → Thread entities
- Edges: PERSON_ASSIGNED_TO_TICKET, TICKET_BELONGS_TO_PROJECT, COMMENT_ON_TICKET, etc.
- Webhook receiver for live updates (ticket status change, new comment, new ticket, etc.)
- Backfill on first connect; webhooks keep current after
- Tests: mock Linear API → assert entities normalized correctly; mock webhook payloads → assert live updates flow

**Branch:** `phase-12-linear-connector`

### Phase 13 — Studio shell + right-panel surfaces
**Goal:** The studio UI users see when they hit the production URL. Welcome, Connect Source, Brain, AGENT/RECEIPTS/HISTORY/SKILLS panels.

- Welcome screen: "Connect a source" with options grid (Linear, Slack, Gmail, Drive, GitHub — placeholders for connectors not yet built)
- Source connection flow per source type
- Right panel: BRAIN / AGENT / RECEIPTS / HISTORY / SKILLS tabs (5 not 4 — SKILLS is its own surface in this build, not buried in the brain inspector)
- BRAIN tab: entity inspector with connections, source provenance, confidence pill, signed-receipt indicator
- AGENT tab: live event stream (signed agent actions from Phase 10, lazy-mount, virtualized)
- RECEIPTS tab: list of all signed receipts with verify status, click-to-verify
- HISTORY tab: chronological brain mutation feed (entity-scoped when entity selected, brain-global otherwise)
- SKILLS tab: list of emitted SKILL.md files with sign attestation, click to view source, click to copy MCP load command
- Approval queue UI: pending DENY actions awaiting human review, allow/deny buttons (decisions signed)
- Tests: each panel renders, regression on previous panel content, performance with full data load

**Branch:** `phase-13-studio-shell`

### Phase 14 — Demo workspace + content + landing page
**Goal:** Production URL is shareable. Anyone hitting it gets a clear sense of what AXIOM does within 30 seconds.

- Landing page at root: short pitch, "See the demo brain" button, "Connect your workspace" button
- Demo brain pre-populated with synthetic Linear-shaped data (60-80 entities, looks like a real small company workspace)
- Demo brain navigable without auth — visitors can click around, see the 3D brain, see particles, see signed receipts
- "Connect your workspace" requires email signup (basic gate to track interest, not user accounts)
- Tutorial overlay on first load: 6 hotspots explaining BRAIN/AGENT/RECEIPTS/HISTORY/SKILLS + the Connect flow
- Pricing page placeholder (decide pricing in OD4)
- About page with founder info
- Tests: landing page renders, demo brain navigable in headless browser, signup flow works

**Branch:** `phase-14-demo-content`

### Phase 15 — End-to-end smoke + YC application material
**Goal:** Everything works together. Application copy drafted with founder. Video demo recorded as backup.

- End-to-end test: visitor → landing → demo brain → signup → connect Linear → real brain populates → agent loads a skill via MCP → action signed → receipt visible → CORRECT mode triggers on out-of-policy attempt → human approval flow works
- Performance test: 1000+ entities in brain, 60 FPS held, all panels responsive
- Security review: secrets not exposed, OAuth tokens encrypted at rest, signed receipts non-forgeable
- YC application copy drafted (see Section 4 — YC Application strategy)
- 60-second demo video recorded as backup in case partners can't access live URL
- Press kit: screenshots, architecture diagram, pricing (TBD), founder photos
- README on GitHub points at production URL + has architecture overview
- Tests: full smoke suite passes, deployment is reproducible, rollback procedure documented

**Branch:** `phase-15-launch-ready`

---

## SECTION 3 — DEFERRED / OUT OF SCOPE FOR LAUNCH

These do not block YC application but are queued for post-launch.

- **Multi-tenant** — single-tenant per workspace at launch. Multi-tenant Postgres migration is its own slice. Not blocking.
- **Slack connector** — Phase 12 ships Linear; Slack is the next connector after launch (it's the most YC-pitch-differentiated but heaviest OAuth, save for post-MVP).
- **Gmail, Drive, GitHub connectors** — same pattern as Slack, ship one per week post-launch.
- **Calibra Layer 1** — AXIOM-BRAIN imports whatever Calibra ships. Layer 1 capabilities (PAUSE response mode in policy, advanced Bayesian features) wire in when ready.
- **Cross-source entity resolution** — same Person across Slack/Linear/Gmail unifies into one Person entity. Designed in schema, deferred to post-launch slice.
- **Skills runtime sandbox** — AXIOM emits skills, agents execute in their own runtime (Cursor, Claude Code, etc.). A first-party runtime is post-launch product decision.
- **Multi-agent debate / argument-back lenient mode** for CORRECT — strict mode (3 strikes) ships at launch; lenient with negotiation comes later.
- **Live cryptographic verification across the wire** — each receipt has verify-status indicator stub at launch; real-time verification gets a post-launch slice.
- **Calendar, CRM (Salesforce/HubSpot), Notion connectors** — same pattern as other connectors, queued for post-launch.
- **Counterfactual brain forking** — preview a change before committing. Post-launch.
- **Agent quarantine** — isolate suspected-drifting agent. Post-launch.
- **Signed brain merging** — two brains reconcile via Merkle proofs. Post-launch.
- **Open-source layer split** — what's MIT vs commercial. See OD3.

---

## SECTION 4 — YC APPLICATION STRATEGY

### Positioning
> "AXIOM is the company brain Tom Blomfield asked for, implementing the closed-loop architecture Diana Hu described — turning every company into a queryable, governed, agent-operable system. Three things no one else ships: 3D visual brain agents and humans both navigate, post-quantum signed actions on every read and write, and three-mode policy (ALLOW/CORRECT/DENY) where most violations get corrected mid-task instead of blocking."

### Two YC partners point at this product (load-bearing)
- **Tom Blomfield** wrote the Company Brain RFS asking for "an executable skills file for AI" and "a living map of how a company works"
- **Diana Hu** wrote "The AI Operating System for Companies" RFS asking for "the connective layer that makes a company legible to AI by default" and "a self-improving loop"
- Application opens by citing both (signal, not noise — both partners review S26 applications)

### Demo flow (what partners click into)
1. Hit landing page → "See the demo brain" → 3D brain populated with 60 synthetic entities renders, particles streaming through
2. Click an entity → BRAIN tab shows connections, confidence (Calibra), signed-receipt indicator (AXIOM)
3. Switch to AGENT tab → see signed agent actions streaming in real-time
4. Switch to RECEIPTS tab → click a receipt → live verify works, returns "verified" with public key
5. Switch to SKILLS tab → see emitted SKILL.md files, click to view source
6. Open the policy engine demo: simulated agent attempts an out-of-policy action → CORRECT signal returned with guidance → agent retries successfully → both attempts signed and visible
7. "Connect your workspace" CTA → email signup → Linear OAuth → user's real workspace populates

### Differentiation in 3 sentences
1. "Universal company brain (not code, not docs, not chat — every company)" — covers Blomfield's universal scope.
2. "Three-mode governance: most violations get corrected mid-task instead of blocking — closed-loop inside the action layer, not at human approval queue" — covers the unique differentiator no other governance vendor ships.
3. "Post-quantum signed every action, not just final entities — verifiable agent provenance for the next 30 years" — covers the moat.

---

## SECTION 5 — OPEN DECISIONS (need founder ruling before they unblock)

### OD1 — Domain name for production
Need before Phase 11. Candidates:
- `axiom.work`
- `getaxiom.com`
- `axiom.brain` (likely unavailable / weird TLD)
- `axiomcontrol.com` (matches company name)
- `useaxiom.com`

Default unless overridden: research availability and shortlist 3 options before Phase 11; founder picks.

### OD2 — Single-tenant vs multi-tenant at launch
Default: single-tenant SQLite for launch (one workspace per AXIOM instance). Multi-tenant Postgres is post-launch when paying customers materialize.

If you want multi-tenant from day 1 because you expect 10+ workspaces immediately, say so and Phase 2 schema changes.

### OD3 — Open-source split
What's MIT vs. commercial?
- AXIOM core (schema + ingest + studio + MCP server): MIT? Or proprietary with self-host license?
- Connectors (Linear, Slack, etc.): MIT or commercial?
- Policy engine + sign-on-action: MIT or commercial?
- Calibra integration: depends on Calibra's own license

Default vote: AXIOM core MIT (drives developer adoption and YC partner appeal — open-source company brain). Connectors MIT. Multi-tenant management, hosted version, cross-source entity resolution, advanced Calibra features = commercial.

### OD4 — Pricing model
Today's memory has dev-seat tiers ($149/$499/mo) which don't fit a company-brain product (CISOs/COOs/ops, not developers). Suggested rethink:
- **Free** — self-hosted, single workspace, basic policy, OSS edition
- **Pro** — hosted, single workspace, full policy engine, $99-299/mo
- **Team** — hosted, multi-workspace, cross-source entity resolution, $999-2999/mo per company
- **Enterprise** — on-prem option, custom policy, SLA, audit support, $50K-500K/yr
- **Compliance Vault** — air-gapped deployment, regulated industries, $250K-1M/yr

Decide before Phase 14 (landing page needs pricing reference).

### OD5 — Co-founder vesting (Gagan)
Equity established. Vesting agreement not executed. Schedule with corporate counsel before YC application. Standard 4-year with 1-year cliff. Not a code task.

### OD6 — Calibra license clarity
Calibra is your own work in `~/brain-experiments/`. License terms for it being imported into AXIOM-BRAIN need to be explicit. Easy if both are wholly yours. Document in repo.

### OD7 — What to do with the 18-file untracked stash
Stash from old OMNIX work (`slice-19-5-untracked-prework`). Now that we're scratch-rebuilding, options:
- Discard entirely (cleanest)
- Salvage anything that's reusable as reference material → copy patterns into AXIOM-BRAIN where useful, then discard the stash

Default: discard. AXIOM-BRAIN is fresh. Old stash was OMNIX-specific in-progress work.

---

## SECTION 6 — RISK VIEW

### Build risk: low
- Scratch architecture eliminates accumulated mess
- Library imports for crypto correctness eliminate the highest-stakes failure mode
- Calibra external import keeps research code isolated and properly tested
- Founder demonstrated 26+ tested phases/day pace
- Hosted-production from day 1 keeps deployment in scope, no late surprises

### Technical risk: medium-low
- WebGPU has hardware/browser variance (some corporate browsers still on WebGL1) — Phase 4 needs WebGL fallback path or explicit WebGPU requirement notice
- Linear OAuth: Linear's API is well-documented but webhook reliability needs production validation
- Hosting platform's WebSocket support varies — verify Fly.io and Render before committing
- 3D rendering at 60+ FPS on AMD Radeon 840M was confirmed on Three.js + WebGPU previously, but the brain envelope distribution in 3D is new work — perf might need tuning

### Calibra dependency risk: low
- Layer 0 capabilities ship today (12 MCP tools, 448 tests). AXIOM-BRAIN works with Layer 0 from day 1.
- Layer 1 ships in 4-8 weeks; AXIOM-BRAIN consumes whenever ready, no dependency on Layer 1 for launch.

### YC acceptance risk: moderate-favorable
- Two YC partners (Hu + Blomfield) explicitly asked for what's being built
- Hosted-production demo at submission removes "is this real" concern
- Three-mode policy + post-quantum signing are genuine differentiators no one else ships
- Risk: if S26 deadline already passed and target is W26/27 batch, calendar permits more polish

### Strategic risk: low
- Naming convention locked, no AXIOM/OMNIX confusion
- IDE-residue eliminated by starting fresh (the persistent friction in OMNIX)
- Code-as-default eliminated (universal entity model from line 1)
- "Humans set policy, agents work automatically, AXIOM force-corrects" architecture locked

### Co-founder dynamics risk: medium (operational, not technical)
- Equity established; vesting unsigned. Schedule with counsel before YC application. Not a code task; a corporate-hygiene risk that becomes acute at investor due diligence.

---

## SECTION 7 — META

### Working principles (carried forward)
- Tests-first per phase
- Per-phase commits, no squashing
- Branch per phase off previous phase tip
- `--no-open` for any local studio launches
- `/tmp/cursor-sandbox-cache` cleanup at start of each Cursor dispatch
- Ruflo best-effort, ripgrep ground truth
- 60+ FPS floor on visual changes
- Don'ts before Dos in every dispatch
- Each Cursor dispatch as `.md` in `/mnt/user-data/outputs/`
- godmode + godmode-engineer-prompter compose for every dispatch; webcraft-ultra adds for visual phases
- AXIOM is the product name. AXIOM-BRAIN is just the repo. OMNIX is retired.
- Code is one of seven entity types, never the default

### Estimated calendar
At demonstrated pace (26+ tested phases/day across two repos):
- Phases 0-5 (design + foundation + first visual): ~1 day
- Phases 6-10 (MCP + Calibra + skills + policy + signing): ~1.5-2 days
- Phases 11-15 (hosted + Linear + studio shell + demo + launch): ~2 days

Total estimated: **4-5 days of focused shipping** to hosted production demo. Add 2-3 days for OAuth debugging, hosting platform quirks, performance tuning. Realistic: **1 week to launch-ready hosted demo**.

### What this roadmap is NOT
- Not a marketing document
- Not the YC application copy itself (drafted in Phase 15)
- Not a competitive analysis
- Not a fundraising deck

It is the build plan. Other artifacts reference this as ground truth.

---

## APPENDIX A — Tom Blomfield's Company Brain RFS (verbatim)

> "The biggest blocker to AI automation of companies is no longer the models, they just got so good so quickly. Now the blocker is the domain knowledge.
>
> Every company has critical know-how scattered everywhere. Some of it lives in people's heads. Some of it is buried in old email accounts, Slack threads, support tickets, and databases. The company works because humans vaguely remember where that knowledge is and how to apply it.
>
> But AI agents can't operate like that. If we want every company to run on AI automation, we need a new primitive: a company brain.
>
> We need Garry's G-Brain, but for every business in the world. A system that pulls knowledge out of all these fragmented sources, structures it, keeps it current, and turns it into an executable skills file for AI.
>
> This isn't a company-wide search or a chatbot over documents. It's a living map of how a company works: how refunds get handled, how pricing exceptions are decided or how engineers respond to incidents.
>
> Then AI systems can use that skills file to actually do the work safely and consistently.
>
> The company brain becomes the missing layer between raw company data and reliable AI automation.
>
> I think every company in the world is going to need one."

## APPENDIX B — Diana Hu's "The AI Operating System for Companies" RFS (verbatim)

> "The best AI-native companies we're seeing have figured out something most haven't: they've made their entire company queryable. Every meeting recorded, every ticket tracked, every customer interaction captured, all legible to an intelligence layer that learns from it.
>
> This turns a company from an open loop into a closed loop. In an open loop, you make a decision and maybe check the results weeks later. In a closed loop, the system monitors what's happening, compares it to what should be happening, and adjusts. I've seen teams that do this cut sprint time in half and ship twice as much.
>
> The problem is building this today requires brutal integration work, stitching together Slack, Linear, GitHub, Notion, call recordings, and a dozen other tools with custom glue code. There's no product that connects all this context into a single intelligence layer that can reason across it, flag when engineering is building the wrong thing, or generate specs agents can execute on.
>
> We think there's a big opportunity to build the connective layer that makes a company legible to AI by default. Not another dashboard. The system that turns a company's own artifacts into a self-improving loop."

---

## Next concrete action

Forge **Phase 0 dispatch** for Cursor: schema design, interface design, MCP tool surface design, policy YAML schema, skills emitter schema, hosting topology design. Output `DESIGN.md` in repo root. HALT for review before Phase 1 starts.

Composition: godmode + godmode-engineer-prompter (no webcraft-ultra in Phase 0 — it's design recon, not visual work). Same standing rules. Branch: `phase-0-design`.

Ready to forge on confirmation.
