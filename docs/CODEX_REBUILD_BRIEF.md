# AXIOM COMPANY BRAIN — ONE-SHOT VISUAL REBUILD BRIEF FOR CODEX

**You are a senior frontend + 3D graphics engineer. This is a ONE-SHOT BUILD. Read this entire brief before writing any code. Then implement everything end-to-end and verify visually before stopping.**

---

## §0 — STARTING STATE

- **Repo:** `~/AXIOM-BRAIN`
- **Branch:** `phase-5-living-brain`
- **Last clean commit:** `e3166c2` (force-directed cluster layout)
- **Backend:** FastAPI on `http://127.0.0.1:8000` (already running — do not touch)
- **Frontend dev server:** Vite/React/Three.js on `http://127.0.0.1:5173`

**Real data is flowing:** 5,187 entities, 11k+ edges, WebSocket live updates working. Data layer is fine. **The visual is wrong.** Your job is the visual only.

**Do NOT modify:**
- Backend code (`src/axiom/**`)
- Data flow (`brain.store.ts`, `websocket.ts`, bootstrap fetches in Brain.tsx)
- The package.json dependencies (no new npm packages)

**You CAN modify or replace:**
- All Three.js rendering code in `frontend/src/components/Brain.tsx` (980 LOC)
- All cluster/satellite/conduit/particle helpers in `frontend/src/lib/`
- All chrome components: `App.tsx`, `SourcesRail.tsx`, `InspectorPanel.tsx`, `LedgerRibbon.tsx`, `BottomToolbar.tsx`, `CommandPalette.tsx`
- CSS in `frontend/src/styles/globals.css`
- Create new files freely under `frontend/src/components/` and `frontend/src/lib/`

---

## §1 — THE TARGET (BINDING)

**Reference image:** `docs/refs/AXIOM_REFERENCE_TARGET.png`

**STUDY THE IMAGE BEFORE CODING. Open it. Look at it. Match it as closely as possible.**

### Target visual breakdown

The reference shows a **dark cinematic 3D knowledge graph** with these elements:

**Background:**
- Deep navy/black background (`#05050A`)
- Faint hex grid texture overlay (~5% opacity)
- Tiny star particles scattered (~50-100 sparse points)

**Two primary clusters in center:**
- **COMPANY KNOWLEDGE** (cyan `#00E5D8`) — large central glowing hex hub surrounded by ~30-50 hex satellites in concentric rings, dense bloom glow around hub
- **EXECUTION CONTEXT** (electric blue `#2B7FFF`) — same structure, slightly smaller, blue color

**Five-to-seven peripheral small clusters scattered organically:**
- **POLICIES** (mint teal `#4DD3B8`) — top left, ~6-10 satellites
- **CUSTOMERS** (mint teal `#4DD3B8`) — far left, ~6-10 satellites
- **RECEIPTS** (mint teal `#4DD3B8`) — bottom left, ~6-10 satellites
- **AGENTS** (purple `#8B5CF6`) — top right, ~6-10 satellites
- **INCIDENTS** (blue `#2B7FFF`) — far right, ~6-10 satellites
- **GOVERNANCE** (deep indigo `#6B4FE0`) — bottom right, ~6-10 satellites

**Inter-cluster connections:**
- Curved 3D Bezier paths between cluster hubs
- **Discrete dot-particles flow along paths** — this is critical. NOT continuous lines. Dotted-particle trails. 4-8 particles per active conduit, traveling continuously.
- Particles glow with additive blending, color-graded source-to-destination

**Cluster anatomy (per cluster):**
- 1 large central hex prism hub (radius 3.6, height 0.6, strong emissive)
- 8-12 inner-ring hexes (radius 2.2, prominent)
- 15-30 mid-ring hexes (radius 1.6)
- Outer scattered hexes (radius 0.9-1.4) for depth
- Subtle internal connecting lines (opacity 0.10-0.15) between adjacent satellites within a cluster
- Cluster glow field — large additive disc behind hub matching cluster color

**Cluster labels:**
- Uppercase, monospace, letter-spaced
- Two lines: NAME (14px, weight 600) + entity count meta (11px, weight 400)
- Thin bracket/leader line connecting label to hub
- Positioned OUTWARD from hub, with viewport-edge guard (flip if would clip)

**Motion (subtle, premium, slow):**
- Hub breathing: ±5% emissive intensity, 4s sine wave
- Satellite shimmer: ±5% scale, 6s period
- Particle flow: continuous, 8-12s end-to-end
- Hover bloom: 200ms scale to 1.15x
- Camera zoom on click: 800ms ease-in-out cubic

### Color palette (LOCKED — replace current rainbow)

```
PRIMARY CYAN     #00E5D8    Company Knowledge + knowledge_flow edges
PRIMARY BLUE     #2B7FFF    Execution Context + Incidents + context_route edges
MINT TEAL        #4DD3B8    Customers / Policies / Receipts (peripheral)
PURPLE VIOLET    #8B5CF6    Agents
DEEP INDIGO      #6B4FE0    Governance
WARN ORANGE      #FF8B3D    Risk signals (rare)
SOFT WHITE       #E8F0FF    Provenance / labels
BG NEAR-BLACK    #05050A    Scene background
HEX GRID DIM     #0F1A2A    Background hex grid
LABEL TEXT       rgba(232,240,255,0.85)
LABEL META       rgba(232,240,255,0.55)
```

---

## §2 — UI CHROME (REPLACE EVERYTHING)

The reference shows a complete UI shell. The current chrome (left "SOURCES" rail, right "THE COMPANY BRAIN" inspector, bottom ledger box, AXIOM v0.1 toolbar) does NOT match. Replace it.

**Build these new components:**

### 2.1 Left vertical icon nav (`<NavRail />`)

- Fixed left edge, ~56px wide
- Vertical strip of icon buttons:
  1. AXIOM hex glyph (top, brand)
  2. Brain (current, active — cyan accent + thin left bar)
  3. Explore
  4. Agents
  5. Insights
  6. Governance
  7. Settings (bottom)
  8. Account avatar (bottom)
- Use lucide-react icons (already installed)
- Active item: cyan accent + thin left bar
- Tooltip on hover for each icon

### 2.2 Top centered header (`<TopHeader />`)

- Fixed top, centered horizontally
- AXIOM hex glyph + "AXIOM" wordmark
- "LIVE" pill on the right side (cyan dot + "LIVE" text)
- Small "Company Brain" sublabel above wordmark in faint cyan

### 2.3 Top-right BRAIN HEALTH card (`<BrainHealthCard />`)

- Floating glassmorphic panel, top-right, ~280px wide
- Header: "BRAIN HEALTH" + colored dot ("Healthy")
- Rows (use REAL backend numbers from `brain.store.ts`):
  - Entities: live count
  - Relationships: live edge count
  - Events / min: rolling 60s average from WebSocket
  - Confidence Avg: mean of `composite_importance` across entities × 100
  - Health: percentage from `cluster_health` aggregate
- Health row has a tiny sparkline below (60s history of health, 3px tall, cyan stroke)

### 2.4 Bottom centered query bar (`<QueryBar />`)

- Floating glassmorphic, horizontally centered, ~50% viewport width
- Sits ~80px from bottom
- Search icon (left) + input (placeholder: "Ask the Company Brain anything...") + ⌘K chip + send button (right)
- Below the input: row of 5 prompt chips:
  - "Who owns payroll integration?"
  - "What decisions affect billing?"
  - "Which policy governs customer data?"
  - "Show systems impacted by PAY-1234"
  - "What changed after the Q2 strategy decision?"
- Clicking a chip fills input + triggers a placeholder traversal animation (camera pans through 2-3 random clusters)
- Focusing input opens existing `CommandPalette.tsx` dialog

### 2.5 Bottom-right edge legend (`<EdgeLegend />`)

- Small glassmorphic, bottom-right, ~180px wide
- 4 rows: colored dot + label
  - Cyan — Knowledge
  - Blue — Execution
  - Purple — Governance
  - Mint — External

### 2.6 Right entity inspector (`<EntityInspector />`)

- Slides in from right when entity/cluster clicked, ~360px wide
- When entity selected:
  - Header: entity name + type badge + status pill
  - Subheader: id + owner
  - Tab strip: Overview / Connections / Lineage / Activity (only Overview functional, others are stub tabs)
  - Overview tab:
    - Description (from entity.data)
    - Owner / Team / Criticality (Low/Med/High pill) / Last updated / Confidence bar
  - Trust & Governance section:
    - Policy Status: Compliant / Flagged
    - Signed Receipt: Verified
    - Merkle Root: hash with copy button
    - Data Sources: small icons
  - Connected Entities (max 10 visible, "View all (N)" link)
- When cluster hub clicked: header is cluster name + entity count, list of entities scrollable

### 2.7 Bottom status footer (`<StatusFooter />`)

- Thin strip full-width bottom
- Left: AXIOM v0.1
- Center: tabs (Graph / Flow / Governance / Timeline / Search / Receipts / Agent Console) — Graph is active, others stub
- Right: FPS counter + "All systems operational" green dot

### 2.8 DELETE these old chrome components:

- `frontend/src/components/SourcesRail.tsx` (replaced by NavRail)
- `frontend/src/components/InspectorPanel.tsx` (replaced by EntityInspector)
- `frontend/src/components/LedgerRibbon.tsx` (replaced by StatusFooter)
- `frontend/src/components/BottomToolbar.tsx` (replaced by StatusFooter)

Keep `CommandPalette.tsx` — used by QueryBar.

### 2.9 Modify `frontend/src/App.tsx`

Replace its current children with:
```tsx
<div className="relative h-screen w-screen overflow-hidden bg-[#05050A]">
  <NavRail />
  <TopHeader />
  <BrainHealthCard />
  <div className="fixed inset-0 left-[56px] right-0">
    <Brain />
  </div>
  <QueryBar />
  <EdgeLegend />
  <EntityInspector />
  <StatusFooter />
  <CommandPalette />
</div>
```

---

## §3 — 3D GRAPH REBUILD (THE HARD PART)

Current `Brain.tsx` is 980 LOC. Refactor it heavily. Don't rewrite from scratch — preserve the bootstrap, WebSocket, store integration, OrbitControls, post-processing/bloom. Replace the cluster/satellite/conduit rendering.

### 3.1 Cluster mapping (frontend reframe — backend stays)

The 7 backend clusters get reframed into 8 visible super-clusters:

```ts
// frontend/src/lib/cluster-reframe.ts (already exists from Phase 5.12.2)

const CLUSTER_REFRAME = {
  // Primary mappings — preserve current Phase 5.12.2 logic
  decisions_policy: 'company_knowledge',
  customer_support: 'company_knowledge',
  growth_product: 'company_knowledge',
  engineering_code: 'execution_context',
  incidents_ops: 'execution_context',
  people_teams: 'people_teams',
  billing_payments: 'billing',
};

// Type-based split-outs
function reframeEntity(entity: Entity): SuperClusterId {
  if (entity.type === 'customer') return 'customers';
  if (entity.type === 'policy') return 'policies';
  if (entity.type === 'incident') return 'incidents';
  if (entity.type === 'agent') return 'agents';
  if (entity.type === 'receipt') return 'receipts';
  if (entity.type === 'governance' || entity.type === 'merkle_proof') return 'governance';
  return CLUSTER_REFRAME[entity.cluster_id] ?? 'company_knowledge';
}
```

This already exists. Verify it works. The 8 super-clusters are:
- `company_knowledge` (primary, cyan)
- `execution_context` (primary, blue)
- `customers` (peripheral, mint)
- `policies` (peripheral, mint)
- `receipts` (peripheral, mint)
- `agents` (peripheral, purple)
- `incidents` (peripheral, blue)
- `governance` (peripheral, indigo)
- `people_teams` (peripheral, mint) — keep
- `billing` (peripheral, mint) — keep

**If you find that some super-clusters end up with zero entities** (Receipts, Agents, Governance, Incidents), that's because the backend doesn't emit those entity types. Fix this by:
1. Pulling from `cluster_health` data for those (synthetic placeholder entities)
2. OR aggregate from existing entities by relationship (e.g., if entity has `agent_signed_by` field, treat as Agents-related)
3. OR accept fewer visible clusters and ensure at least 6 clusters always render with content

The ZERO-ENTITY problem is the biggest current blocker — **make sure every visible cluster has at least 6 satellite hexes rendering**, even if synthetic. The graph must look populated.

### 3.2 Cluster centroids — force-directed layout (already exists)

`frontend/src/lib/cluster-force-layout.ts` exists from Phase 5.12.3. Keep using it. But TUNE the parameters:

- Increase repulsion strength so primary clusters don't pile up in the center
- Cap maximum primary-to-primary distance (Knowledge ↔ Execution should be visible together but not piled)
- Spread peripherals in a wider radius around the primaries

Target final positions (after force layout + normalization to ±100/±60/±30):
- Primary 1 (Knowledge): roughly center-left, X ≈ -25, Y ≈ 0, Z ≈ 0
- Primary 2 (Execution): roughly center-right, X ≈ +30, Y ≈ +5, Z ≈ -5
- Peripherals fan out around them organically

If force layout produces ugly results, fall back to **hand-placed centroids that match the reference image's general topology**:

```ts
const REFERENCE_CENTROIDS = {
  company_knowledge:  new Vector3(-30,  0,   0),
  execution_context:  new Vector3( 35,  5,  -5),
  policies:           new Vector3(-50, 35,  10),
  customers:          new Vector3(-80, -5,   5),
  receipts:           new Vector3(-30,-40,   0),
  agents:             new Vector3( 60, 35, -10),
  incidents:          new Vector3( 75, -5,   0),
  governance:         new Vector3( 60,-35,  -5),
  people_teams:       new Vector3(  0, 25,  15),
  billing:            new Vector3( 10,-25,  10),
};
```

Use these if force layout looks bad. Pragmatism over algorithm purity.

### 3.3 Satellite packing — concentric 3D rings

`frontend/src/lib/satellite-pack.ts` exists from Phase 5.12.4. Verify it produces concentric rings (not a tight ball). If it doesn't, REWRITE.

Algorithm:
- For a cluster with N entities and clusterRadius R:
  - **Inner ring:** 8 satellites on a sphere of radius `0.30 * R` — these are the prominent "first ring"
  - **Mid ring:** `min(N - 8, 16)` satellites on sphere of radius `0.65 * R`
  - **Outer ring:** rest of entities (or up to 30) on sphere of radius `R`
- Use **spherical Fibonacci lattice** within each shell for even distribution
- Apply ±5-8% radial jitter for organic feel (deterministic via mulberry32 seeded by cluster ID hash)
- **Per-instance hex radius:**
  - Inner ring: `HEX_NODE_RADIUS * 1.4` (= 2.24 if base is 1.6)
  - Mid ring: `HEX_NODE_RADIUS * 1.0`
  - Outer ring: `HEX_NODE_RADIUS * 0.7`

**Cluster radius (R) per cluster — REVISED for visual balance:**

```ts
const CLUSTER_RADIUS = {
  company_knowledge: 22,  // primary
  execution_context: 20,  // primary
  customers:          8,
  policies:           7,
  receipts:           7,
  agents:             8,
  incidents:          8,
  governance:         8,
  people_teams:       9,
  billing:           10,
};
```

Smaller than previous spec — too-large clusters were overlapping in the screenshot.

### 3.4 Hub geometry

- Hub: hex prism, radius 3.6, height 0.6
- Strong emissive: `emissiveIntensity = 2.0`
- Inner glowing core (separate small sphere mesh inside hub, additive blend, color matching cluster, 50% smaller than hub)
- Outer halo: separate sprite or sphere mesh around hub, additive blend, faded gradient, ~3x hub size

### 3.5 Satellite geometry

- Hex prism, base radius `HEX_NODE_RADIUS = 1.6`, height 0.4
- Per-instance scale via InstancedMesh `setMatrixAt`
- Per-instance color via InstancedMesh color attribute (one cluster color per cluster's satellites)
- Emissive intensity ~0.6 (dimmer than hub)

### 3.6 Inter-cluster conduits — DOTTED PARTICLE FLOWS

This is the critical visual. Reference image's conduits are NOT continuous lines. They're **streams of discrete glowing dots** flowing along curved paths.

**Replace `frontend/src/lib/curved-conduits.ts` and `frontend/src/lib/particle-flow.ts`:**

For each significant inter-cluster connection (top 10-15 by edge count):

1. **Compute Bezier curve** in 3D from sourceHub → targetHub:
   - Use a control point offset perpendicular to the line, scaled by distance × 0.3
   - Vary curve direction per-connection (alternate above/below) for visual variety

2. **Spawn 4-8 particles per conduit:**
   - Each is a small additive-blended Points or Sprite mesh
   - Particles travel along the curve at speed ~0.0015 t/frame
   - Each particle has a phase offset so they're evenly distributed
   - When a particle reaches t=1.0, it loops back to t=0.0
   - Color: gradient from source cluster color (at t=0) to target cluster color (at t=1)
   - Size: 0.4-0.6 world units
   - Emissive: 1.5

3. **Curve path itself**: very dim line (opacity 0.08) just so the path is barely visible — particles are the focus

4. **On hover/focus**: particles speed up 2x and conduit line opacity goes to 0.4

### 3.7 Intra-cluster web

Within each cluster, draw thin connecting lines between satellite hexes:

- For each satellite, find 1-2 nearest neighbors within the same cluster
- Draw THREE.LineSegments with:
  - Opacity 0.08
  - Additive blending
  - Color matching cluster
- Don't make these the visual focus — they're texture, not structure

### 3.8 Background

- Add `frontend/src/lib/hex-grid-bg.ts` (or modify existing `HexGridBackground.tsx`):
  - Plane geometry behind everything, far Z
  - Hex grid texture (procedural via shader OR static SVG converted to texture)
  - Color `#0F1A2A`, opacity 0.05
  - Subtle radial gradient overlay around scene center, slightly cyan
- Add star particles:
  - 80 small white points scattered randomly in a sphere of radius 200 around scene center
  - Size 0.3-0.6 world units
  - Opacity varies 0.3-0.8 per particle
  - Very slow drift (0.05 t/frame) to feel alive

### 3.9 Cluster labels (CSS2DRenderer)

Already in place via `ClusterBracketLabel.tsx`. Tune:

- Position: outward from cluster centroid, distance = `clusterRadius + 12` in world units
- **Edge guard:** if label position would clip viewport (X > viewport.right - 200 OR Y < viewport.bottom + 100), flip the direction
- Format:
  ```
  COMPANY KNOWLEDGE
  1,066 entities · 2.2k relationships
  ```
- Font: monospace, uppercase
- First line: 14px, weight 600, letter-spacing 0.18em, color `#E8F0FF` at 0.85 opacity
- Second line: 11px, weight 400, letter-spacing 0.10em, color `#E8F0FF` at 0.55 opacity
- Bracket leader line: thin SVG line from label to hub, color matching cluster, opacity 0.5
- ALL labels inside `.axiom-labels` container with `padding: 16px` for edge clearance

Drop the "CRITICAL" / "HEALTHY" pills shown in current screenshot — they don't appear in reference. Cluster health is conveyed via hub glow color, not text badges.

### 3.10 Camera

- OrbitControls (already in place) — keep
- Initial position: `(0, 0, 280)` looking at origin
- Min distance: 60 (so user can't zoom into a single hex)
- Max distance: 400
- Idle slow rotation: ±0.3 rad/sec around Y when no user interaction for 5+ seconds (use `IdleOrbitController.ts` already in place)

### 3.11 Click interactions

- Click cluster hub → camera flies to cluster centroid + EntityInspector slides in showing cluster overview
- Click satellite → camera flies to satellite + EntityInspector shows entity details
- Click empty space → clear selection, camera flies back to default
- Esc → clear selection
- ⌘K → focus QueryBar / open command palette

### 3.12 Bloom & post-processing

`UnrealBloomPass` already configured. Tune:
- `strength = 0.8` (currently might be 1.4 — reference is more restrained)
- `radius = 0.5`
- `threshold = 0.15`

---

## §4 — IMPLEMENTATION ORDER

Suggested sequence (you can deviate if you find a better order):

1. **Read the reference image** at `docs/refs/AXIOM_REFERENCE_TARGET.png`. Look at it for 60 seconds before coding.

2. **Read `frontend/src/components/Brain.tsx`** end-to-end. Understand the bootstrap, scene setup, render loop, WebSocket integration. Don't touch the data flow.

3. **Verify cluster reframe** — open `frontend/src/lib/cluster-reframe.ts`. Confirm 8 super-clusters defined. If any are emitting zero entities at runtime, address per §3.1.

4. **Replace cluster geometry** — hubs (3.6 radius prisms with glow), satellites (3-ring concentric packing per cluster), per-instance varied size.

5. **Replace inter-cluster conduits** — discrete dotted particle flows, not continuous lines.

6. **Add intra-cluster web** — thin opacity-0.08 lines between adjacent satellites.

7. **Add background** — hex grid + star particles.

8. **Tune labels** — edge guard, formatting, drop CRITICAL pills.

9. **Update color palette** — replace current rainbow with cool palette (cyan/blue/purple/mint).

10. **Build chrome components** — NavRail, TopHeader, BrainHealthCard, QueryBar, EdgeLegend, EntityInspector, StatusFooter.

11. **Modify App.tsx** to use new chrome.

12. **Delete old chrome** — SourcesRail, InspectorPanel, LedgerRibbon, BottomToolbar.

13. **Tune bloom + camera + motion** — match reference's premium feel.

14. **Run frontend tests** — `cd frontend && npm test -- --run`. Update broken assertions if any. Don't ship if tests below 270 passing.

15. **Open localhost:5173 in browser. Compare to reference image side by side. Iterate on the visual until it matches.**

---

## §5 — ACCEPTANCE CRITERIA

The build is done when ALL of these are true:

1. **Visual match:** Side-by-side screenshot of localhost:5173 vs reference image — clear resemblance (cluster topology, hex constellation aesthetic, dotted particle flows, premium dark feel).

2. **No empty clusters:** Every visible cluster has at least 6 satellite hexes rendering. No "empty colored circles" like the current state.

3. **Hub dominance:** Each cluster has a clearly visible large central hex hub (3.6 radius). Hubs are not buried in satellites.

4. **Concentric rings:** Each cluster shows visible inner / mid / outer ring structure with size variation, NOT a tight ball of uniform dots.

5. **Particle flows:** Inter-cluster conduits show discrete glowing dot-particles flowing along curved Bezier paths. NOT continuous solid lines.

6. **Cool palette:** Cyan / blue / purple / mint / indigo throughout. No red / lime / yellow / pink.

7. **New chrome:** NavRail (left icons), TopHeader (centered AXIOM), BrainHealthCard (top-right), QueryBar (bottom-center with prompt chips), EdgeLegend (bottom-right), EntityInspector (right slide-in on click), StatusFooter (bottom strip).

8. **Real data:** Entity counts, edge counts, events/min — all real from backend, updating live.

9. **Performance:** ≥55 FPS at 5,000+ entities.

10. **Tests:** ≥270 passing, ≤10 failing (the 5 known CompanyBrainPage interaction failures are acceptable).

11. **Working tree commits:** Single comprehensive commit at end:
    ```
    git add -A
    git commit -m "phase 5.12.4-12: full visual rebuild to match reference image"
    ```

---

## §6 — IF YOU GET STUCK

- **If a Three.js technique is unclear:** check what's already in `frontend/src/lib/` — there are existing patterns for InstancedMesh, particles, conduits, AEGIS rings, idle orbit, FPS guard. Use them as templates.

- **If a cluster has zero entities:** synthesize placeholder hexes from cluster_health metadata. Better to show 6 hexes than empty circles.

- **If force layout looks bad:** fall back to `REFERENCE_CENTROIDS` from §3.2.

- **If labels collide:** implement edge-flip logic per §3.9. After force layout, re-check label positions against final cluster positions.

- **If performance drops below 55 FPS:** reduce satellite count per cluster (cap at 30 for primaries, 8 for peripherals), reduce particle count per conduit (4 instead of 8), or reduce conduit count (top 10 by edge count instead of all).

- **If you can't match a reference detail exactly:** prioritize the overall feel (hex constellation aesthetic, dark cinematic, particle flows, premium chrome) over pixel-perfect color matching.

---

## §7 — DELIVERABLE

After implementation:

1. Running localhost:5173 shows the visual matching the reference image
2. Tests passing at ≥270/5
3. Single commit with all changes
4. Brief summary report:
   - Files created (list)
   - Files modified (list)
   - Files deleted (list)
   - What works
   - What's still rough (if anything)
   - Any deferred items

---

**END OF BRIEF. Begin implementation.**
