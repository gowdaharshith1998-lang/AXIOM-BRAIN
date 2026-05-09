# Reboot Checkpoint — after Phase 5.13.1

Date: 2026-05-09 (late)
Branch: main
Last commit: d8e17f6 phase 5.13.1: provider registry + key verification
Tests: pytest 172/0, vitest 249/0
Vault: AXIOM_VAULT_KEY in .env, key rotation completed cleanly

## Phase 5.13 ladder progress
- [x] 5.13.0 vault foundation — 26b8d83
- [x] 5.13.1 provider registry + verify — d8e17f6
- [ ] 5.13.2 vault HTTP API endpoints ← NEXT
- [ ] 5.13.3 settings page UI
- [ ] 5.13.4 wire classifier to use vault
- [ ] 5.14.0 query layer (the original "make prompt chips work" goal)

## Resume protocol
  1. cat NOTES.md | head -50
  2. git log --oneline -8
  3. git status (must be clean)
  4. set -a; source .env; set +a; echo "Vault: ${#AXIOM_VAULT_KEY}"
  5. pytest -q | tail -3 (must show 172 passed)
  6. cd frontend && npm test -- --run --reporter=basic | tail -3 (249 passed)
  7. Reboot Cursor — fresh composer
  8. Send Phase 5.13.2 prompt

---

# Reboot Checkpoint — after Phase 5.13.0 vault foundation

Date: 2026-05-09
Branch: main
Last commit: 26b8d83 phase 5.13.0: vault foundation — encrypted secrets storage
Tests: pytest 147 / 0, vitest 249 / 0
Vault: AXIOM_VAULT_KEY in .env, smoke test verified

## Phase 5.13 ladder progress
- [x] 5.13.0 vault foundation (encrypted secrets storage) — 26b8d83
- [ ] 5.13.1 provider registry + verify ← NEXT
- [ ] 5.13.2 vault HTTP API endpoints
- [ ] 5.13.3 settings page UI
- [ ] 5.13.4 wire classifier to use vault
- [ ] 5.13.5+ OAuth flows for Google/Microsoft

## Tier 1 polish completed earlier today
- [x] f3b4b7a README rewrite to match reality
- [x] 920e44c audit docs committed
- [x] 4b914e9 dead company-brain/ tree deleted
- [x] 78bff4b synthetic governance → demo labels
- [x] 26b8d83 vault foundation

## Resume protocol for next Cursor session
  1. cat NOTES.md
  2. git log --oneline -8
  3. git status
  4. Confirm AXIOM_VAULT_KEY loaded in shell
  5. pytest -q && cd frontend && npm test -- --run --reporter=basic | tail -5
  6. Begin Phase 5.13.1

---

# NOTES — AXIOM-BRAIN

# Reboot Checkpoint — after Phase 5.12.3 (Force layout)

Date: 2026-05-09
Branch: phase-5-living-brain
Last commit: e3166c2 (force-directed cluster layout)
Tests: 275 passed / 5 failed (CompanyBrainPage interaction tests, known)

## Phase 5.12 ladder progress:
- [x] 5.12.0 lock spec + reference image (a3ea305)
- [x] 5.12.1 spike scaffolding removed (58bc376)
- [x] 5.12.2 cluster reframe + cool palette (45d66df)
- [x] 5.12.3 force-directed cluster layout (e3166c2)
- [ ] 5.12.4 organic satellite packing + size variation ← NEXT
- [ ] 5.12.5 discrete particle conduits
- [ ] 5.12.6 edge typing
- [ ] 5.12.7 intra-cluster web
- [ ] 5.12.8 chrome part 1 (NavRail + TopHeader + StatusFooter)
- [ ] 5.12.9 chrome part 2 (BrainHealthCard + QueryBar + EdgeLegend)
- [ ] 5.12.10 entity inspector
- [ ] 5.12.11 query traversal animation
- [ ] 5.12.12 polish

## Phase 3 APPROVED PLAN — execute in next session

Goal: each cluster transforms from "ball of dots" into "1 large hub
+ concentric rings of varied-size hexes."

Files to CREATE:
- frontend/src/lib/satellite-pack.ts
  - packSatellites({centroid, count, clusterRadius, seed}) → SatellitePosition[]
  - 3 rings: inner (8-12 sats, 0.35*radius), mid (35%, 0.65*radius), outer (rest, 1.0*radius)
  - Spherical Fibonacci lattice per shell + 7.5% radial jitter
  - Per-instance hex radius: inner 1.4x, mid 1.0x, outer 0.7x
  - mulberry32 seeded PRNG for determinism
- frontend/src/__tests__/satellite-pack.test.ts
  - Determinism, ring split correctness, bounds, per-ring radius

Files to EDIT:
- frontend/src/lib/cluster-layout.ts
  - Add CLUSTER_RADIUS = {company_knowledge: 28, execution_context: 25,
    customers: 12, policies: 10, receipts: 10, agents: 11, governance: 11,
    billing: 14, people_teams: 12}
- frontend/src/lib/hex-geometry.ts
  - HEX_HUB_RADIUS: 2.4 → 3.6
  - HEX_NODE_RADIUS: 1.0 → 1.6
- frontend/src/lib/hex-layout.ts
  - Extend VisibleEntitySlot: add hexRadius: number, ring: 0|1|2
  - Rewrite computeVisibleEntitySlots to use packSatellites per cluster
  - Keep MAX_VISIBLE_PER_CLUSTER, CLUSTER_VISIBLE_SLOTS exports for backcompat
- frontend/src/components/Brain.tsx
  - Drop mesh.scale.setScalar(1.3) on hubs (HEX_HUB_RADIUS now 3.6)
  - In setInstanceTransform: add ringScale = slot.hexRadius / HEX_NODE_RADIUS
    multiplied into existing scale chain
- frontend/src/__tests__/hex-layout.test.ts
  - Add assertions: every slot.hexRadius in {1.6*1.4, 1.6*1.0, 1.6*0.7}
  - Primary cluster max satellite distance ≤ CLUSTER_RADIUS * 1.08
- frontend/src/__tests__/cluster-mesh.test.ts (test helper)
  - Add hexRadius default in local VisibleEntitySlot helper
- frontend/src/__tests__/radial-traffic.test.ts (test helper)
  - Add hexRadius default in local VisibleEntitySlot helper

Visual expectation:
- Hubs visibly dominant at 3.6-radius
- Inner ring 8-12 prominent hexes (radius 2.24)
- Mid + outer rings at 1.6 / 1.12 radii
- Knowledge/Execution clusters noticeably larger
- Peripheral clusters tighter
- Organic 3D constellation, not flat rings

Resume protocol for next session:
  1. cat docs/AXIOM_PHASE_5_12_SPEC.md (full spec)
  2. cat NOTES.md (this checkpoint)
  3. git log --oneline -10
  4. git status (confirm clean tree)
  5. Run backend (port 8000) + frontend (port 5173)
  6. Begin Phase 5.12.4 Phase B (execute) — Phase A is APPROVED above

## END CHECKPOINT

---

## 2026-05-08 — Phase 5.11 checkpoint (pre-Phase 5 implementation)

- **Context budget**: ~57% used / ~43% remaining (Cursor session estimate)
- **Spec gate**: Phase 2 (patched R1–R14) accepted; Candidate A collapse accepted
- **Reference**: `docs/refs/PHASE_5_11_TARGET_REFERENCE.png` (dense hex constellation target)
- **Scope lock**:
  - SVG overlay is the primary target: `frontend/src/components/company-brain/*`
  - Three.js underlay `frontend/src/components/Brain.tsx` is **read-only** for Phase 5.11
- **Phase 4 status**:
  - Added 4 new test files under `frontend/src/components/company-brain/__tests__/`
  - Latest run (`frontend`, `npm test`): **23 tests failing** (expected red-state)
  - New tests currently assert structural DOM requirements (no image diffs); `"FALLBACK"` regression is included
- **Coverage audit (pre-Phase 5 gate)**:
  - Missing clause-tests to add before Phase 5 begins:
    - R5 live “breathing” animation hook (assert real animation marker/class/style exists in non-reduced-motion)
    - R13 per-cluster centroid positions (assert each of 14 clusters renders at expected xFrac/yFrac ± tolerance)
    - R14a keyboard Tab order (user-event tab loop through all 14 clusters in order)
  - R14b prefers-reduced-motion has a structural marker test; may be tightened to assert no breathe/drift markers.
- **Next actions (still Phase 4, before any Phase 5 code)**:
  - Add 3 tests (one per missing clause above)
  - Re-run `frontend` tests and reconfirm **all new tests red**
  - Then begin Phase 5.11.1 atomic commit: HexConstellation primitive + tests

# Phase 5.11 Trajectory Checkpoint (context @ 57%)

STATE: Phase 4.5 — RED-STATE 26/26 confirmed (post-hardening). Implementation not yet started.
BRANCH: phase-5-living-brain
NEXT: Phase 5.11.1 (HexConstellation primitive)

PATHS LOCKED (do not re-Recon):

Modify:
- frontend/src/components/company-brain/CompanyBrainPage.tsx
- frontend/src/components/company-brain/CompanyBrainGraph.tsx
- frontend/src/components/company-brain/companyBrainData.ts
- frontend/src/state/brain.store.ts
- frontend/src/lib/cluster-layout.ts
- frontend/src/lib/curved-conduits.ts (extend)
- frontend/src/lib/particle-flow.ts (extend)

Add:
- frontend/src/components/company-brain/HexConstellation.tsx
- frontend/src/components/company-brain/Conduit.tsx
- frontend/src/components/company-brain/HubNode.tsx
- frontend/src/components/company-brain/ErrorBanner.tsx
- frontend/src/hooks/useBrainFocus.ts

DO NOT modify:
- frontend/src/components/Brain.tsx (Three.js, read-only)
- src/axiom/** (backend, read-only)

STACK LOCKED (do not re-Recon):
- Vite 5.4 + React 18.3 + TS 5.5 + zustand 5 + Tailwind 3.4
- Tests: vitest 2.0 + RTL 16 + jsdom 24
- Test command: cd frontend && npm test -- --run
- Animation primitives: SMIL animateMotion + CSS keyframes only
- Forbidden deps: framer-motion, gsap, react-spring, user-event, jest-image-snapshot, pixelmatch, three.js (already there for Brain.tsx but new usages forbidden)

BACKEND CONTRACT LOCKED:
- GET /api/entities returning EntityDTO[]
- GET /api/edges returning EdgeDTO[]
- GET /api/cluster_health returning Record<cluster_id, ClusterHealthDTO>
- WS /ws/brain?since=<seq> with events: entity.created, entity.updated, entity.removed, edge.created, edge.removed, cluster.health, ingest.heartbeat

TAB_ORDER constant:
- Exported from frontend/src/lib/cluster-layout.ts
- Type: readonly string[]
- Imported by both impl (CompanyBrainGraph) and test (interaction test)

COMMIT LADDER (9 commits, in this order):
- 5.11.1 HexConstellation primitive
- 5.11.2 Conduit primitive
- 5.11.3 HubNode extracted
- 5.11.4 useBrainFocus state machine
- 5.11.5 ClusterNode wired to HexConstellation
- 5.11.6 CompanyBrainGraph rebuilt; conduits use new primitive
- 5.11.7 companyBrainData dataMode patched; FALLBACK_* deleted
- 5.11.8 WS subscription + ErrorBanner + cb-data-mode span removed
- 5.11.9 full suite green; FPS verified greater-than-or-equal 55; manual e2e

REFLEXION GUARD:
- ITER_COUNT tracked from Phase 5.11.1 start
- At iter 3 RED → emit TRIED / WHY / ROOT / PIVOT before any further code change
- At iter 5 RED → HALT, surface for human review

GOVERNING INSTRUCTION:
End-to-end at localhost:5173 visually matches docs/refs/PHASE_5_11_TARGET_REFERENCE.png AND every interaction R6–R9 works AND the literal "FALLBACK" string is gone from DOM.

TOKEN DISCIPLINE:
- Per commit emit only: file diff + 3-line rationale + test pass count
- Do not re-paste large file contents unless asked
- Do not re-cite the spec — locked above
- After 5.11.4 (mid-ladder) update this section with latest commit hash + active ITER_COUNT + assess if compaction needed

FRESH-CONTEXT REBOOT PROTOCOL:
If context exceeds 80%:
1. Stop at the next commit boundary
2. Update this NOTES.md section with latest commit hash + ITER_COUNT + which step landed
3. Start fresh Cursor composer
4. First message in fresh context: "cat NOTES.md, then continue Phase 5.11.<next>"
5. Do not re-Recon

═══ ACTIONS ═══

1. Update R14a test per Item 1; re-run; confirm RED 26/26 (post-hardening).
2. Append the Item 2 block VERBATIM to NOTES.md (plain text, not in a code fence).
3. After both done, proceed to Phase 5.11.1 (HexConstellation primitive).
   First commit on phase-5-living-brain.
   Reflexion clock starts at iter 0.

═══ END ═══

---

## Reboot Checkpoint — after 5.11.2

Date: 2026-05-08
Last commit on phase-5-living-brain: 8ddf46a
Last commit message: phase 5.11.5: ClusterNode wired to HexConstellation (28/40 green)
Test state: 28 / 40 new tests passing · 245 prior frontend tests still green
Reflexion: ITER_COUNT was 0 throughout 5.11.1–5.11.5 (no Reflexion triggered)
Context budget: ~35% (estimate)
REBOOT RECOMMENDED: no (well below 75% threshold)
RuFlo MCP: installed, but `ruflo:*` plan/execute/verify/checkpoint tools still not exposed (carry-forward to 5.11.6)

Files created so far (5.11.1–5.11.5):
- frontend/src/components/company-brain/HexConstellation.tsx
- frontend/src/components/company-brain/Conduit.tsx
- frontend/src/components/company-brain/HubNode.tsx
- frontend/src/components/company-brain/ClusterNode.tsx
- frontend/src/hooks/useBrainFocus.ts
- (plus matching test harness mods)

Next step: 5.11.6 (CompanyBrainGraph rebuild; conduit + focus wiring).
Resume protocol: in fresh Cursor session, first action is `cat NOTES.md`,
second action is `git log --oneline -10`, then begin 5.11.6.

Phase 5.11.6 cleanup todo:
- Remove onLegacyHover prop from ClusterNode
- Remove hoveredCluster useState from CompanyBrainPage
- Replace selectedId prop with focus.clusterId from store
- Remove is-active className path in CompanyBrainGraph; cb-dimmed becomes the sole highlight system
- Remove cb-cluster.is-active CSS rules (or merge into cb-cluster-node rules)

Note: HexConstellation gained optional aria props (ariaHidden/ariaLabel) in 5.11.5 so the interactive ClusterNode wrapper can be the single accessible target without duplicate "People cluster, N entities" matches in RTL queries.

DO NOT re-Recon. Paths and stack locked at top of NOTES.md.
DO NOT re-cite the spec. EARS R1–R14 already locked.
DO NOT chase Data tests yet — that's 5.11.7+.

---

## 5.11.6 Approved Plan — captured at context 75% before reboot

State: Phase A complete + reviewed + 3 items resolved. Phase B not started.
Branch: phase-5-living-brain
After 5.11.5 HEAD: 8ddf46a
Cumulative: 28/40 green
Reflexion: ITER_COUNT 0 throughout 5.11.1-5.11.5

DISCOVERY findings (locked):

1. Click handling: lives in ClusterNode.tsx via onSelect prop, wired
   through CompanyBrainGraph → CompanyBrainPage (chooseCluster +
   selectedCluster/selectedId). No other graph-level click handlers
   to preserve.

2. Esc test: fires fireEvent.keyDown(window, { key: "Escape" }) — must
   be window/document-level listener. Tests render <CompanyBrainPage />
   for Esc/click/backdrop/entity/hover; Tab test renders
   <CompanyBrainGraph /> directly. Listener placement: CompanyBrainPage
   is correct (Item 1 = CASE A).

3. visibleClusters sort: currently maps in viewModel.clusters order
   (whatever that is). Must sort by TAB_ORDER index before mapping
   so DOM order = TAB_ORDER for the keyboard cycle test.

4. Entity rendering: test 5 renders <CompanyBrainPage /> which mounts
   <Brain /> (Brain.tsx handles /api/entities fetch via mockFetchOk
   and calls useBrainStore.getState().bootstrap(...)). Entity glyphs
   must render when focus.mode === "FOCUS_CLUSTER" using entities
   from useBrainStore(s => s.entities).

ENTITY GLYPH DOM CONTRACT (locked):
  - Sibling group: <g data-role="entity-layer">
  - Each entity: <g data-role="entity" data-entity-id="<id>"
                    tabIndex={0}
                    aria-label="<entity-name> entity"
                    onClick={(e)=>{e.stopPropagation();
                                   focusEntity("<id>", clusterId);}}
                    onKeyDown={(e)=>{if(e.key==="Enter") focusEntity(...);}}>
                    <circle .../>
                  </g>
  - Position: radial offsets around focused cluster centroid (small radius)
  - Visual polish deferred to 5.12.

cb-dimmed CLAUSE (locked, both clauses preserved):
  - Apply when (focus.mode in {FOCUS_CLUSTER, FOCUS_ENTITY}
                && focus.clusterId !== cluster.id)
  - OR when (focus.mode === "AMBIENT" && hoveredClusterId !== null
                                       && hoveredClusterId !== cluster.id)
  - Note: current ClusterNode.tsx is missing the FOCUS_ENTITY clause;
    fix in Phase B.

PLANNED FILE DIFFS:
- ClusterNode.tsx : modified — remove onLegacyHover, selectedId, onSelect;
                     use useBrainFocus() inside; compute cb-hovered/
                     cb-focused/cb-dimmed; call focusCluster on click/Enter.
- CompanyBrainGraph.tsx : modified — remove selectedId/hoveredId/onSelect/
                           onHover props; add stage aria-label; add
                           backdrop <rect data-role="brain-backdrop">
                           as first SVG child; sort visibleClusters by
                           TAB_ORDER; render ClusterNode only; add
                           entity-layer rendering for focused cluster.
- CompanyBrainPage.tsx : modified — remove hoveredCluster useState;
                          remove selectedId/hoveredId prop wiring; add
                          useBrainFocus(); use focus.clusterId for
                          inspector; useEffect(() => hydrateFromUrl(), []);
                          install document keydown listener for Escape →
                          clearFocus().
- useBrainFocus.ts : modified — expose hydrateFromUrl, clearFocus,
                      focusEntity (in addition to existing exports).
- brain.store.ts : modified (minimal) — focus actions are sole selection
                    source of truth; no new state shape.
- styles/company-brain.css : modified — remove .cb-cluster.is-active rules;
                              add .cb-cluster-node.cb-focused styling.
- NOTES.md : modified — mark 5 cleanup todos as done in commit emit.

PHASE B EXECUTION ORDER (9 steps):
  STEP 1: Apply 5 cleanup todos. Run vitest. Verify 28/40 still green.
          (Hover tests must stay green; click/Esc tests stay red.)
  STEP 2: Sort visibleClusters by TAB_ORDER. Run vitest. Tab test green: 29/40.
  STEP 3: Wire cluster click → focusCluster. Add cb-focused. Run vitest.
          Click + URL hash tests green: ~31/40.
  STEP 4: Add backdrop <rect> + click handler. Run vitest. Backdrop
          test green: 32/40.
  STEP 5: Add Esc keydown listener (document-level in CompanyBrainPage).
          Run vitest. Esc test green: 33/40.
  STEP 6: Add entity glyph rendering + click handler. Run vitest. Entity
          test green: 34/40.
  STEP 7: Add hydrateFromUrl() on CompanyBrainPage mount. Run vitest.
          Confirm 34/40 stable.
  STEP 8: Browser visual check (mandatory, 5-point list — see below).
  STEP 9: Emit COMMIT 5.11.6 in locked format.

BROWSER VISUAL 5-POINT CHECK (mandatory before COMMIT-READY):
  cd frontend && npm run dev
  Open http://127.0.0.1:5173 (or 5174) IN A BROWSER
  Verify:
    1. 14 hex constellations render
    2. Click cluster → focused, others dim, URL hash → #cluster=<id>
    3. Press Esc → focus clears, hash clears
    4. Click background → focus clears, hash clears
    5. Tab cycles focus through clusters
    6. Chrome DevTools console: zero errors, zero warnings beyond baseline
  Kill dev server.
  IF anything breaks → RETRY iter 1 with diagnosis.

REFLEXION CLOCK:
  At iter 3 RED → emit TRIED/WHY/ROOT/PIVOT before next code change.
  Most likely trigger: entity-rendering test (test 5) — depends on
  bootstrap path + aria-label + focusEntity all aligning.

5.11.5 CLEANUP TODOS (Part A — 5 items, all due in Phase B step 1):
  1. Remove onLegacyHover prop from ClusterNode + callsite
  2. Remove hoveredCluster useState from CompanyBrainPage
  3. Replace selectedId prop with focus.clusterId from store
  4. Remove is-active className path in CompanyBrainGraph
  5. Remove .cb-cluster.is-active CSS (or merge into cb-cluster-node)

CONTEXT BUDGET AT REBOOT: 75% used in prior session
NEXT ACTION IN FRESH CONTEXT: cat NOTES.md, then begin 5.11.6 Phase B
                                step 1 (cleanup todos)

---
