# NOTES — AXIOM-BRAIN

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
Last commit on phase-5-living-brain: 599e656
Last commit message: phase 5.11.4: useBrainFocus state machine + tests (6/6 green, 24/38 total)
Test state: 24 / 38 new tests passing · 245 prior frontend tests still green
Reflexion: ITER_COUNT was 0 throughout 5.11.1–5.11.4 (no Reflexion triggered)
Context budget: 27%
REBOOT RECOMMENDED: no (well below 75% threshold)
RuFlo MCP: installed, but `ruflo:*` plan/execute/verify/checkpoint tools still not exposed (carry-forward to 5.11.5)

Files created so far (5.11.1–5.11.4):
- frontend/src/components/company-brain/HexConstellation.tsx
- frontend/src/components/company-brain/Conduit.tsx
- frontend/src/components/company-brain/HubNode.tsx
- frontend/src/hooks/useBrainFocus.ts
- (plus matching test harness mods)

Next step: 5.11.5 (ClusterNode wired to HexConstellation + hover state).
Resume protocol: in fresh Cursor session, first action is `cat NOTES.md`,
second action is `git log --oneline -10`, then begin 5.11.5.

Phase 5.11.6 cleanup todo:
- Remove onLegacyHover prop from ClusterNode
- Remove hoveredCluster useState from CompanyBrainPage
- Replace selectedId prop with focus.clusterId from store
- Remove is-active className path in CompanyBrainGraph; cb-dimmed becomes the sole highlight system
- Remove cb-cluster.is-active CSS rules (or merge into cb-cluster-node rules)

DO NOT re-Recon. Paths and stack locked at top of NOTES.md.
DO NOT re-cite the spec. EARS R1–R14 already locked.
DO NOT chase Data tests yet — that's 5.11.7+.
