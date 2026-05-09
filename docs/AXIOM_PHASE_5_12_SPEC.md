# AXIOM COMPANY BRAIN — PHASE 5.12 REBUILD SPEC

**Reference image:** `docs/refs/AXIOM_REFERENCE_TARGET.png` (the cyan + blue + purple Company Brain image with COMPANY KNOWLEDGE / EXECUTION CONTEXT clusters)

**Branch:** `phase-5-living-brain`

**Last clean commit:** `58bc376` (phase 5.12.1: spike scaffolding removed)

**This document is binding.** Cursor should reference this file before every commit and check work against acceptance criteria. Do not deviate without approval.

---

## §0 — IDENTITY & SCOPE LOCK

**Product:** AXIOM Company Brain — a live organizational knowledge graph. Humans query it. AI agents traverse it via skills/MCP tools. Provides pre-execution context, governance, lineage, provenance, confidence, and trust.

**This is NOT:**
- A codebase visualization
- A generic admin dashboard
- A force-graph experiment
- An OMNIX clone (OMNIX was visual-style inspiration only)

**This IS:**
- A cinematic 3D living graph that auto-clusters real entities from connected sources (Slack, Linear, GitHub, Notion, Email, Meetings)
- A queryable surface — humans type questions, AI agents call MCP tools
- An operator tool with governance/lineage/receipt visibility
- The hero of the screen — chrome supports the graph, never competes with it

**Out of scope this phase:**
- Backend changes (data ingestion, schema, WebSocket protocol)
- New connector integrations
- Skills marketplace UI
- Authentication/authorization
- Mobile responsive (desktop-first; ≥1440px primary target)

---

## §1 — VISUAL CONTRACT (BINDING)

**Match the reference image as closely as possible.** Every implementation choice must serve this visual.

### 1.1 Graph aesthetic

- Deep navy/black background (#05050A or similar near-black)
- Subtle hex grid texture overlay (faint, ~3-5% opacity)
- Tiny star-like background particles (sparse, ~50-100 points)
- Sparse spatial composition — generous negative space between clusters
- 2 large primary clusters + 5-7 smaller peripheral clusters
- Asymmetric organic placement (NOT a grid, NOT a perfect ring)
- Each cluster: 1 large central glowing hex hub + 5-30 satellite hexes
- Cluster glow / fog field (radial soft light around hub)
- Curved Bezier paths between clusters
- **Discrete dot-particles flowing along paths** (this is critical — not continuous lines, dotted-particle trails)
- Bloom on emissive surfaces (hubs, particles)
- Cluster labels with thin bracket/leader lines

### 1.2 Color palette (LOCKED)

```
PRIMARY CYAN   #00E5D8    Company Knowledge cluster + knowledge_flow edges
PRIMARY BLUE   #2B7FFF    Execution Context cluster + context_route edges
MINT TEAL      #4DD3B8    Customers, Receipts, Policies (small green-cyan clusters)
PURPLE VIOLET  #8B5CF6    Agents cluster
DEEP INDIGO    #6B4FE0    Governance cluster
WARN ORANGE    #FF8B3D    Risk signals, incidents
SOFT WHITE     #E8F0FF    Provenance lines, ambient particles
BG NEAR-BLACK  #05050A    Scene background
HEX GRID DIM   #0F1A2A    Background hex grid
LABEL TEXT     rgba(232,240,255,0.85)   Cluster labels
LABEL META     rgba(232,240,255,0.55)   Entity counts, sublabels
```

**Replace** the current 7-color rainbow (red/lime/green/pink/yellow/cyan/purple) entirely. The cool palette is half the visual identity.

### 1.3 Node geometry

- All nodes are hex prisms (Three.js CylinderGeometry with 6 sides, rotated)
- **Hub nodes:** radius 3.6, height 0.6, strong emissive (intensity 1.8-2.2), inner glowing core
- **Mid-ring satellites:** radius 1.6-2.2, varying randomly within range, height 0.4
- **Outer satellites:** radius 0.9-1.4, height 0.3, dimmer
- All nodes have thin neon stroke (achieved via outline pass OR by adding a slightly larger transparent halo mesh)
- Soft outer halo around each hex (additive-blended sphere or sprite)

### 1.4 Cluster anatomy

Each cluster is composed of:
- 1 hub at cluster centroid (large glowing hex)
- ~6-12 mid-ring hexes in inner ring (radius ~6-10 from hub)
- ~15-30 outer hexes in outer ring (radius ~12-18 from hub), more scattered
- Cluster size scales with entity count:
  - **Primary clusters** (Company Knowledge, Execution Context): 30-60 satellites, scene radius ~25
  - **Peripheral clusters** (Policies, Agents, etc.): 5-15 satellites, scene radius ~10
- Internal edges: thin glowing lines (opacity 0.15) connecting nearest neighbors within cluster (max 2 edges per node)
- Cluster glow field: large additive-blended disc behind hub, color matching cluster, fades to transparent edge

### 1.5 Inter-cluster conduits

- Curved 3D Bezier paths between cluster hubs
- Edge type determines visual style (see §3 Edge Types)
- Particles flow along paths in discrete dots (not continuous lines)
- 4-8 particles per active conduit, evenly spaced, traveling at speed proportional to traffic
- Particle size 0.4-0.6, additive blending, color-graded from source to destination cluster color
- Path opacity 0.35-0.55 default, 0.85 when source or destination is hovered/focused
- Inactive paths dim further (opacity 0.15)

### 1.6 Labels

Each cluster has a 2-line label with a bracket/leader line:

```
COMPANY KNOWLEDGE
1,247 entities · 18.2K relationships
```

- Uppercase, monospace (ui-monospace, Menlo, Monaco)
- Heading: 14px, weight 600, letter-spacing 0.18em, color #E8F0FF at 0.85 opacity
- Meta line: 11px, weight 400, letter-spacing 0.10em, color #E8F0FF at 0.55 opacity
- Bracket line: thin (1px) line from label to cluster hub, color matching cluster, opacity 0.5
- Position: anchored OUTWARD from cluster hub, offset 14-18 in screen units, but with viewport-edge guard (flip if would clip)
- Render via CSS2DRenderer (already in place)

### 1.7 Motion design

All motion is subtle, premium, slow:
- Hub breathing: ±5% emissive intensity oscillation, 4s period, sine wave
- Satellite shimmer: tiny scale variation 0.95-1.05, 6s period, per-node phase offset
- Particle flow: continuous along conduits, 8-12 seconds end-to-end
- Hover bloom: 200ms ease-in-out scale up to 1.15
- Selection ring: 250ms ease-out fade-in, then static
- Camera zoom on click: 800ms ease-in-out cubic, ends framing the cluster
- No chaotic movement, no rotation animations, no pulsing borders

---

## §2 — DATA MODEL & AUTO-CLUSTERING

**Backend stays untouched.** Real entities/edges flow from existing FastAPI endpoints (`/api/entities`, `/api/edges`, `/api/cluster_health`, `/ws/brain`).

### 2.1 Cluster reframe (Q1 = c)

The 7 backend clusters get reframed into super-clusters in the frontend layer:

| Reference label | Backend cluster IDs | Color |
|---|---|---|
| **COMPANY KNOWLEDGE** | `decisions_policy`, `customer_support`, `growth_product` | Cyan |
| **EXECUTION CONTEXT** | `engineering_code`, `incidents_ops` | Blue |
| **CUSTOMERS** | (subset of `customer_support` — entities of type `customer`) | Mint Teal |
| **POLICIES** | (subset of `decisions_policy` — entities of type `policy`) | Mint Teal |
| **RECEIPTS** | (synthetic, derived from ledger entries) | Mint Teal |
| **AGENTS** | (synthetic — Claude, Cursor, GPT-5 from sources rail) | Purple |
| **GOVERNANCE** | (synthetic, derived from AEGIS gate state) | Deep Indigo |
| **PEOPLE & TEAMS** | `people_teams` | Mint Teal (peripheral) |
| **BILLING** | `billing_payments` | Mint Teal (peripheral) |

This reframe is done in a new file `frontend/src/lib/cluster-reframe.ts` that maps backend `cluster_id` to frontend `super_cluster_id`. Backend doesn't need to change. **8-9 visible clusters total.**

### 2.2 Auto-clustering (LIVE)

Per your spec — "it should build automatically alive for whatever it's connected to and sort all the files in the right clusters."

The graph layout is computed on the frontend each time bootstrap data arrives:

1. **Group entities by super-cluster** using `cluster-reframe.ts`
2. **Compute cluster centroids** using force-directed simulation (`cluster-force-layout.ts`):
   - Inter-cluster edge counts as attraction weights
   - Repulsion between all clusters (inverse-square)
   - Soft gravity pull toward origin
   - 200 iterations, dt=0.05, damping=0.85
   - Returns Record<SuperClusterId, THREE.Vector3>
3. **Place satellites within each cluster** using spherical Fibonacci lattice + jitter (`satellite-pack.ts`)
4. **Compute inter-cluster conduits** by aggregating cross-cluster edges (`conduit-aggregator.ts`)

When new entities arrive via WebSocket:
- Append to entity store (already happens)
- If entity belongs to existing super-cluster: pack into next available satellite slot, animate fade-in
- If entity introduces a new cluster connection: emit a particle on the corresponding conduit
- Re-run force layout only on full bootstrap (not on every event — would be too jittery)

### 2.3 Edge types & visual mapping

| Edge type | Visual | Color | When to use |
|---|---|---|---|
| `knowledge_flow` | Dotted curved path with cyan particles | Cyan #00E5D8 | docs/meetings/decisions flowing into Company Knowledge |
| `context_route` | Solid curved glowing path | Blue #2B7FFF | AI agent traversal, code/system relationships |
| `governed_by` | Thin luminous purple path | Purple #8B5CF6 | Policy/governance links |
| `risk_signal` | Pulsing warn-colored path | Orange #FF8B3D | Incidents, vendor risk, criticality |
| `provenance_link` | Faint dotted soft-white line | White #E8F0FF | Lineage, receipts, proof chain |

If backend doesn't currently emit edge types, default all edges to `context_route` and add edge typing in a follow-up phase.

### 2.4 Real numbers, not fake (Q5 = real)

The BRAIN HEALTH card shows the actual backend numbers:
- Entities: live count from store (currently 5,187)
- Relationships: live edge count (currently 10,613)
- Events/min: rolling 60s average from WebSocket events
- Confidence avg: average of `composite_importance` across entities (or 0 if not present)
- Health: from `/api/cluster_health` aggregate
- Health sparkline: rolling 60s history of health scores

**No fake numbers anywhere in production code.** Demo numbers are for the reference image only.

---

## §3 — UI CHROME (FULL REPLACEMENT)

Per Q3 = all yes — replace `SourcesRail`, `InspectorPanel`, `LedgerRibbon`, `BottomToolbar` entirely.

### 3.1 Left icon nav (`<NavRail />`)

Vertical strip, ~56px wide, fixed left edge. Dark surface, faint right-edge border.

Items, top to bottom:
1. AXIOM hex glyph (top, brand)
2. **Brain** (current page, active)
3. **Explore**
4. **Agents**
5. **Insights**
6. **Governance**
7. (spacer)
8. **Settings** (bottom)
9. **Account avatar** (bottom)

Each item: 40x40 icon button, lucide-react icon, label appears on hover as tooltip. Active item: cyan accent + thin left bar.

Files: `frontend/src/components/NavRail.tsx`

### 3.2 Top header bar (`<TopHeader />`)

Centered, top of viewport, ~64px tall. Contains:
- Centered AXIOM wordmark + hex glyph
- LIVE pill on the right of wordmark (cyan dot + "LIVE" text)
- Tiny meta text "Company Brain" above wordmark in faint cyan

Files: `frontend/src/components/TopHeader.tsx`

### 3.3 Top-right BRAIN HEALTH card (`<BrainHealthCard />`)

Floating panel, top-right of viewport, ~280px wide. Glassmorphic surface (rgba background + backdrop-blur).

Contents (real backend values, see §2.4):
- Header: "BRAIN HEALTH" + colored dot ("Healthy" / "Degraded" / "Offline")
- Entities: count
- Relationships: count
- Events / min: rolling
- Confidence Avg: percentage
- Agents Active: count from sources rail (Claude/Cursor/GPT-5 etc.)
- Health: percentage with sparkline below

Sparkline: 60s history, 3px tall, cyan stroke, transparent fill.

Files: `frontend/src/components/BrainHealthCard.tsx`

### 3.4 Bottom center query bar (`<QueryBar />`)

Floating, horizontally centered, ~50% viewport width, sits ~80px from bottom edge. Glassmorphic.

Contents:
- Search icon (lucide `Search` or AXIOM hex glyph)
- Input: placeholder "Ask the Company Brain anything..."
- Right side: ⌘K shortcut chip + send button (hex-shaped or arrow)

Below the input, a row of 5 prompt chips:
- "Who owns payroll integration?"
- "What decisions affect billing?"
- "Which policy governs customer data?"
- "Show systems impacted by PAY-1234"
- "What changed after the Q2 strategy decision?"

Clicking a chip fills the input AND triggers a graph traversal animation that highlights the relevant path.

The query input opens a command palette dialog when focused (extends current `CommandPalette.tsx`).

Files: `frontend/src/components/QueryBar.tsx`, modify `CommandPalette.tsx`

### 3.5 Bottom-right color legend (`<EdgeLegend />`)

Compact, bottom-right corner. ~180px wide.

Contents:
- Header: "EDGES" or unlabeled
- 5 rows, each: colored dot + label
  - Cyan dot — Knowledge
  - Blue dot — Execution
  - Purple dot — Governance
  - Mint dot — External
  - Orange dot — Risk
- Collapsible (chevron)

Files: `frontend/src/components/EdgeLegend.tsx`

### 3.6 Inspector panel (`<EntityInspector />`) — replaces `InspectorPanel`

Slides in from RIGHT when an entity or cluster is selected. ~360px wide. Glassmorphic.

When entity selected:
- Header: entity name + type badge (System / Person / Document / Decision / Ticket / etc.) + status pill (Active / Stale)
- Subheader: e.g., "payments-service" + "Owned by Platform Team"
- Tab strip: Overview / Connections / Lineage / Activity
- **Overview tab:**
  - Description (from entity.data)
  - Owner (avatar + name)
  - Team
  - Criticality (Low/Med/High pill)
  - Last updated timestamp
  - Confidence bar with %
- **Trust & Governance section** (always visible):
  - Policy Status: Compliant / Flagged
  - Signed Receipt: Verified (with View link to merkle proof)
  - Merkle Root: hash with copy button
  - Proof: View Merkle Proof link
  - Data Sources: source icons (Slack/Linear/GitHub/Notion/Email)
- **Connected Entities** (collapsible list, max 10 visible, "View all (24)" link):
  - Each row: type icon + entity name + badge
- **This Graph Powers AI Execution** footer:
  - "Pre-execution context — Agents pull verified knowledge before acting"
  - "Governed by policy — Every action is checked, signed, and auditable"
  - "Executable skills — Structured knowledge becomes agent skills"

When cluster selected (no specific entity):
- Header: cluster name + entity count
- List of entities in the cluster (scrollable)
- Click entity → switches to entity view

Files: `frontend/src/components/EntityInspector.tsx`

### 3.7 Bottom status bar (`<StatusFooter />`) — replaces `BottomToolbar` + `LedgerRibbon`

Thin strip at bottom of viewport, full width. Contents left-to-right:
- "AXIOM v0.1" or version
- Mode buttons: Graph / Flow / Governance / Timeline / Search / Receipts / Agent Console
- Far right: FPS counter + "All systems operational" indicator (green dot)

Files: `frontend/src/components/StatusFooter.tsx`

### 3.8 Agent skills indicator (subtle)

Small pill row, bottom-left or appended to StatusFooter:
- "Agent traversal: live"
- Hover to reveal skills:
  - skills_query_company
  - skills_get_entity
  - skills_search_entities
  - skills_traverse_path
  - skills_verify_receipt
  - skills_get_merkle_proof

Compact, never dominates.

Files: extend `StatusFooter.tsx` or new `AgentSkillsPill.tsx`

### 3.9 Mini-map (nice-to-have, deferred)

Bottom-left corner, ~180x120px. Shows full graph topology miniature with viewport indicator. Click to teleport camera.

Defer to Phase 6 polish.

---

## §4 — INTERACTION MODEL (Q4 = all)

### 4.1 Camera & navigation

- OrbitControls already in place (kept)
- Default: idle slow rotation around scene center
- Mouse drag: orbit
- Scroll: zoom (clamped between min/max distance)
- Right-click drag: pan (optional)

### 4.2 Hover

- Hover any entity → entity scales to 1.15x, glow intensifies, immediate edges to that entity highlight at full opacity
- Hover any cluster hub → cluster glows brighter, all conduits to/from that cluster highlight, peripheral clusters dim slightly
- Cursor changes to pointer over interactive elements

### 4.3 Click — entity

- Camera flies to entity (800ms cubic ease)
- Entity gets selection ring (white torus, additive blend)
- Inspector slides in from right with entity details
- Edges from entity to other entities highlight
- Other entities dim
- URL hash updates: `#entity=<id>`

### 4.4 Click — cluster hub

- Camera flies to cluster centroid (zoomed in to frame the cluster)
- Cluster's entities visible and clickable
- Inspector shows cluster overview + entity list
- Other clusters dim
- URL hash updates: `#cluster=<id>`

### 4.5 Click — empty space

- Clear selection
- Camera returns to default idle position (1000ms ease)
- Inspector slides out
- URL hash clears

### 4.6 Keyboard

- `Esc` — clear selection (same as click empty)
- `⌘K` / `Ctrl+K` — focus query bar / open command palette
- `Tab` — cycle focus through clusters (accessibility)
- `Arrow keys` (when entity focused) — cycle to neighboring entities

### 4.7 Query bar interactions

- Focus query bar → command palette opens
- Type query → live suggestions (entity names, cluster names, relationships)
- Submit query → run a "traversal" — the graph animates a path from a starting cluster through relevant entities, particles flow along the path, ends focused on the most relevant entity
- Click a prompt chip → fills input + auto-submits

### 4.8 Live behavior (Q1, Q5 = live)

When backend WebSocket emits an event:
- New entity → fade-in animation at its position, brief halo pulse
- New edge → conduit briefly brightens, particle emits along it
- Entity update → tiny scale pulse on that entity
- Cluster health change → cluster glow color shifts

These animations are subtle — no flashbangs, no noise. The graph feels alive but calm.

---

## §5 — FILE INVENTORY

### 5.1 NEW files to create

```
frontend/src/lib/
  cluster-reframe.ts                   Backend cluster IDs → super-cluster mapping
  cluster-force-layout.ts              3D force-directed cluster centroid layout
  satellite-pack.ts                    Spherical Fibonacci satellite placement
  conduit-aggregator.ts                Aggregate cross-cluster edges into conduits
  edge-type-classifier.ts              Determine edge type (knowledge_flow / context_route / etc.)
  hex-grid-bg.ts                       Subtle hex grid background (modify existing or new)

frontend/src/components/
  NavRail.tsx                          Left vertical icon nav
  TopHeader.tsx                        Centered AXIOM wordmark + LIVE pill
  BrainHealthCard.tsx                  Top-right stats card with sparkline
  QueryBar.tsx                         Bottom search bar with prompt chips
  EdgeLegend.tsx                       Bottom-right color legend
  EntityInspector.tsx                  Right-side entity/cluster inspector
  StatusFooter.tsx                     Bottom status bar
  AgentSkillsPill.tsx                  Compact skills indicator (or merge into StatusFooter)
  HealthSparkline.tsx                  Tiny inline sparkline component
  EdgeParticleFlow.tsx                 Discrete dot-particle conduit (new style)

frontend/src/hooks/
  useEntitySelection.ts                Selection state (entity / cluster / null)
  useGraphTraversal.ts                 Query → animated path through graph
  useLiveStats.ts                      Rolling stats (events/min, health history)

frontend/src/styles/
  brain-theme.css                      Color tokens, type ramp, glass surfaces
```

### 5.2 EXISTING files to modify

```
frontend/src/App.tsx                   Replace child layout: NavRail + TopHeader + Brain (center) + BrainHealthCard + QueryBar + EdgeLegend + EntityInspector + StatusFooter
frontend/src/components/Brain.tsx      Major rewrite — see §6 for the rebuild
frontend/src/lib/cluster-layout.ts     Update CLUSTER_IDS to super-cluster IDs, new CLUSTER_COLORS palette
frontend/src/lib/curved-conduits.ts    Discrete-particle dot trails (currently solid line)
frontend/src/lib/particle-flow.ts      Discrete particle behavior, per-conduit emission
frontend/src/lib/hex-geometry.ts       Tunings: HUB_RADIUS=3.6, NODE_RADIUS variations
frontend/src/state/brain.store.ts      Add selection/traversal slice if not present
frontend/src/styles/globals.css        Replace cluster color CSS variables
```

### 5.3 EXISTING files to DELETE or LEAVE DEAD

```
frontend/src/components/SourcesRail.tsx           Replaced by NavRail (delete or hide)
frontend/src/components/InspectorPanel.tsx        Replaced by EntityInspector (delete)
frontend/src/components/LedgerRibbon.tsx          Replaced by StatusFooter (delete)
frontend/src/components/BottomToolbar.tsx         Replaced by StatusFooter (delete)
frontend/src/components/company-brain/*.tsx       Phase 5.11 SVG experiments (LEAVE DEAD, do not delete)
frontend/src/lib/sphere-geometry.ts               No longer used (delete)
frontend/src/lib/cluster-mesh.ts                  buildIntraClusterMeshGroup gone, but may be reused for subtle webs (decide in Phase 2)
frontend/src/lib/radial-traffic.ts                Replaced by EdgeParticleFlow (delete after migration)
```

### 5.4 Files to LEAVE UNTOUCHED

```
src/axiom/**                            All backend code
frontend/src/main.tsx                   Vite entry
frontend/src/lib/websocket.ts           WS protocol
frontend/src/lib/aegis-gate.ts          Governance ring (kept for cluster glow)
frontend/src/lib/aegis-particles.ts     Kept
frontend/src/lib/idle-orbit.ts          Kept
frontend/src/lib/camera-flyto.ts        Kept (used for click-to-focus)
frontend/src/lib/fps.ts, fps-guard.ts   Kept
```

---

## §6 — BUILD ORDER (PHASES)

Execute in this order. Each phase ends with a commit + visual verification at localhost:5173.

### Phase 0 — Pre-flight (no code)
- Read this spec end-to-end
- Read `Brain.tsx` (980 LOC) end-to-end
- Read all files in §5 inventory that already exist
- Confirm understanding of current state
- Ask clarifying questions before writing code

### Phase 1 — Cluster reframe & color palette (1 commit)
**Goal:** Backend's 7 clusters become 8-9 frontend super-clusters with the new color palette. Visually identical to current state otherwise.

- Create `cluster-reframe.ts`
- Update `cluster-layout.ts` with new `SuperClusterId`, `CLUSTER_COLORS`, `CLUSTER_LABELS`
- Update `globals.css` color tokens
- Modify `Brain.tsx` to use super-cluster IDs throughout
- Tests: existing 274 must stay green. Update any that break due to ID renames.
- Visual: clusters shift to cyan/blue/purple/mint palette. Same grid layout.

**Commit:** `phase 5.12.2: cluster reframe + cool palette`

### Phase 2 — Force-directed cluster layout (1 commit)
**Goal:** Clusters break out of the 3-row grid into organic spacing.

- Create `cluster-force-layout.ts`
- Replace `HEX_CLUSTER_CENTROIDS` usage in `Brain.tsx` with `computeForceClusterLayout(entities, edges)`
- Run on bootstrap, cache result
- Visual: 8 clusters now sit in organic positions, varying Z-depth, asymmetric.

**Commit:** `phase 5.12.3: force-directed cluster layout`

### Phase 3 — Satellite repacking + size variation (1 commit)
**Goal:** Satellites form dense organic balls (concentric rings of varying-size hexes) instead of grid-like radial array.

- Create `satellite-pack.ts` with spherical Fibonacci + jitter
- Modify `hex-layout.ts` (or `Brain.tsx`) to use it
- Vary node radius: hub 3.6, mid-ring 1.6-2.2, outer 0.9-1.4
- Visual: each cluster looks like a glowing ball of varied hexes.

**Commit:** `phase 5.12.4: organic satellite packing + size variation`

### Phase 4 — Discrete particle conduits (1 commit)
**Goal:** Inter-cluster paths look like dotted-particle trails (not continuous lines).

- Create `EdgeParticleFlow.tsx` (or extend `particle-flow.ts`)
- Per active conduit: 4-8 discrete particles, additive blend, color-graded source→target
- Modify `curved-conduits.ts` — keep curve geometry but de-emphasize the line itself; let particles be the dominant visual
- Visual: glowing dots flow along curves between clusters.

**Commit:** `phase 5.12.5: discrete particle conduits`

### Phase 5 — Edge typing (1 commit)
**Goal:** 5 edge types render with their distinct visual styles.

- Create `edge-type-classifier.ts`
- For each edge from backend, classify type based on source/target clusters and entity types
- Apply visual rules from §3
- If backend doesn't emit type, fall back to `context_route`
- Visual: variety of edge styles between clusters (cyan dotted, blue solid, purple thin, etc.)

**Commit:** `phase 5.12.6: edge typing + visual variety`

### Phase 6 — Subtle intra-cluster web (1 commit)
**Goal:** Quiet web feel within each cluster (1-2 thin lines per satellite to nearest neighbors).

- Reuse `cluster-mesh.ts` logic but with maxEdgesPerNode=2, opacity 0.06-0.10, additive blend
- Visual: clusters webbed but not dominated by lines.

**Commit:** `phase 5.12.7: intra-cluster web`

### Phase 7 — Chrome rebuild Part 1 — left + top + bottom (1 large commit, or split)
**Goal:** New navigation/header/footer chrome.

- Create `NavRail.tsx`, `TopHeader.tsx`, `StatusFooter.tsx`
- Modify `App.tsx` to use new chrome
- Delete `SourcesRail.tsx`, `BottomToolbar.tsx`, `LedgerRibbon.tsx`
- Visual: layout shifts to match reference's chrome positions.

**Commit:** `phase 5.12.8: chrome part 1 — nav rail + header + footer`

### Phase 8 — Chrome rebuild Part 2 — health card + query bar + legend (1 commit)
**Goal:** Top-right BRAIN HEALTH card, bottom-center query bar with chips, bottom-right edge legend.

- Create `BrainHealthCard.tsx`, `QueryBar.tsx`, `EdgeLegend.tsx`, `HealthSparkline.tsx`, `useLiveStats.ts`
- Modify `App.tsx` to mount them
- Visual: matches reference image's UI overlays exactly.

**Commit:** `phase 5.12.9: chrome part 2 — brain health + query bar + legend`

### Phase 9 — Inspector rebuild (1 commit)
**Goal:** Replace InspectorPanel with EntityInspector matching reference.

- Create `EntityInspector.tsx`, `useEntitySelection.ts`
- Wire selection state in `brain.store.ts`
- Trust & Governance section reads from real backend data (AEGIS gate, ledger entries)
- Connected Entities reads from edges
- Delete old `InspectorPanel.tsx`
- Visual: clicking an entity slides in detailed inspector matching reference.

**Commit:** `phase 5.12.10: entity inspector with trust & governance`

### Phase 10 — Query traversal animation (1 commit)
**Goal:** Click a prompt chip → graph animates a traversal path.

- Create `useGraphTraversal.ts`
- For each prompt chip, hand-author a traversal path (Phase 11+ would be LLM-generated)
- Animation: sequential cluster highlights, then sequential entity highlights, particle flowing through path, camera pans to final entity
- Visual: prompts feel like actual queries with visual answers.

**Commit:** `phase 5.12.11: query traversal animation`

### Phase 11 — Polish (1-2 commits)
**Goal:** Match reference image as closely as possible.

- Tune emissive intensities (`HUB_EMISSIVE`, `BLOOM_FULL_STRENGTH`, satellite emissive)
- Adjust hex grid background opacity
- Star particle density
- Cluster glow field radius/opacity
- Label placement edge guards (final pass after all clusters in their final positions)
- Bracket leader lines connecting labels to hubs
- Test on different viewport widths (1440, 1920, 2560)
- Performance pass: confirm ≥55 FPS at 5,000+ entities

**Commit:** `phase 5.12.12: polish — match reference image`

---

## §7 — ORCHESTRATION DISCIPLINE

### 7.1 Per-phase protocol

Each phase follows the standard pattern (already proven in 5.11):

1. **Phase A — Diagnostic + Plan (no code).** Cursor reads relevant files, drafts the change plan, lists files modified and rationale. WAITS FOR USER APPROVAL.
2. **Phase B — Execute.** Apply changes, run vitest, capture diff, ask user to reload localhost:5173.
3. **Visual Gate.** User confirms localhost:5173 matches the phase goal. Cursor screenshots for the record (note: Cursor's screenshots may fail without backend — user is the source of truth on visuals).
4. **Commit.** Single logical commit per phase. Format: `phase 5.12.X: <one-line description>`.
5. **NOTES.md update.** Append phase completion summary.

### 7.2 Reflexion clock

- ITER 0 = first attempt
- ITER 3 RED → emit TRIED / WHY / ROOT / PIVOT before continuing
- ITER 5 RED → HALT for user triage

### 7.3 Token budget

- Per Phase B emit: files changed list + 3-line rationale + test delta + status only
- No verbose "I'm thinking about doing X next"
- If context exceeds 75%: emit reboot checkpoint, user starts fresh Cursor session, first command is `cat NOTES.md`

### 7.4 Out-of-scope guardrail

If during a phase Cursor finds itself wanting to:
- Modify backend code → STOP, defer
- Add a new npm dependency → STOP, ask
- Touch files not in §5.1 or §5.2 for that phase → STOP, ask
- Skip ahead to a later phase → STOP, finish current phase first

### 7.5 Test discipline

- Existing 274 passing tests MUST stay passing throughout
- The 11 known-failing CompanyBrainPage tests stay as-is (they test a fixture page that App.tsx never renders — known issue)
- Each new component should have a basic smoke test (renders without crash, renders expected text)
- Visual changes verified by user reload, not by tests (vitest can't see WebGL)

---

## §8 — ACCEPTANCE CRITERIA

The full Phase 5.12 rebuild is accepted only if ALL of these are true:

1. **Visual match.** localhost:5173 looks visually close to the reference image. Screenshots side-by-side make the resemblance obvious.
2. **Identity match.** UI clearly reads as "AXIOM Company Brain" — wordmark visible, governance/lineage/skills concepts visible.
3. **Domain semantics.** Cluster labels are company domains (Knowledge / Execution / Policies / Agents / Governance / Customers / Receipts / Incidents) — NOT codebase labels (Backend / API / Runtime).
4. **Live data.** Entity counts, relationship counts, events/min, confidence — all real from backend, updating live.
5. **Auto-clustering.** When backend data changes, the frontend re-derives clusters and layout automatically. No hand-editing of cluster positions.
6. **Query surface.** A query bar is visible. Typing focuses it. Prompt chips work. ⌘K shortcut works.
7. **Inspector.** Clicking an entity opens a side inspector with real entity data + trust/governance section + connections.
8. **Hover & click.** Hover highlights, click selects, Esc clears. URL hash reflects selection.
9. **Animation.** Particles flow along conduits in real time. Hubs breathe. New entities animate in.
10. **Premium feel.** Dark, cinematic, sparse. Not cluttered. Not a generic dashboard. Graph is the hero.
11. **Performance.** ≥55 FPS at 5,000+ entities on a typical laptop.
12. **Tests.** 274 passing, 11 known-failing (no new regressions).

---

## §9 — KNOWN OUT-OF-SCOPE / FOLLOW-UP PHASES

These are explicitly NOT part of Phase 5.12. Do not attempt:

- LLM-powered query traversal (Phase 5.13+)
- Real MCP skill execution (Phase 5.14+ — Calibra integration)
- Mobile responsive layout
- Mini-map (deferred to polish if time allows)
- Timeline scrubber
- Full backend cluster type system (auto-detect cluster from entity content)
- Entity type icons (defer to Phase 6 polish if time allows)
- Real merkle proof verification UI (currently placeholder)
- Multi-user / collaboration features
- Saved queries / history
- Export to image / video / report

---

## §10 — REFERENCE QUICK INDEX

**Reference image:** `/mnt/user-data/uploads/1778312882824_image.png` (or wherever user has it). Save to `docs/refs/AXIOM_REFERENCE_TARGET.png`.

**Color tokens:** §1.2

**Cluster reframe table:** §2.1

**Edge type table:** §2.3

**File inventory:** §5

**Build order (12 phases):** §6

**Acceptance criteria:** §8

---

**END OF SPEC.**
