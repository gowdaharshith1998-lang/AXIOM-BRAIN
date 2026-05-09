# AXIOM CODEBASE AUDIT — Brief for Claude Code

You are a senior engineer brought in to perform an **honest ground-truth audit** of this codebase before YC submission. The owner has been working on this for weeks under heavy AI agent orchestration (Cursor + Codex CLI) and has lost track of what's actually working vs. scaffolded vs. broken.

Your job: produce a single document, `docs/AXIOM_AUDIT_REPORT.md`, that tells the owner exactly what they have. **No coding. Read-only. Be honest, not flattering.**

---

## §1 — WHAT YOU'RE AUDITING

Repo: `~/AXIOM-BRAIN`
Branch: `main` at HEAD `2a220a1` (or later)

**Project context:** AXIOM Control Systems is building "AXIOM" — pitched as a "company brain" for YC S26 RFS 1.2 (Tom Blomfield's RFS). Pulls knowledge from fragmented sources (Slack, Linear, GitHub, Notion, Email), structures it, classifies it into clusters, governs every AI agent action against policy, signs receipts cryptographically.

**Tech stack:**
- Backend: FastAPI + SQLAlchemy + SQLite, Python
- Frontend: React + Three.js + Vite + TypeScript
- Architecture: ingestion → organizer (cluster classifier) → governance (warden + policy + AEGIS) → signing → ledger

**Phases (per `docs/AXIOM_PHASE_5_12_SPEC.md` and README):**
- Phase 0–2: design + skeleton + schema (claimed done)
- Phase 5.x: Living Brain visualization (claimed done as of `2a220a1`)
- Phase 6+: query layer, Calibra integration, governance policies, merkle anchoring, real connectors (claimed deferred)

---

## §2 — THE AUDIT QUESTIONS

For each subsystem, answer these in the report:

1. **Does it exist?** (file + module check)
2. **Is it wired?** (does it actually run end-to-end, or is it scaffolded but disconnected?)
3. **What does it actually do at runtime?** (read the code; describe behavior, not docstrings)
4. **What would happen if I removed it?** (load-bearing or decorative?)
5. **What's the fastest path to make it real?** (only if currently fake/stub)

---

## §3 — SUBSYSTEMS TO AUDIT

Walk through these in order. Spend ~10 minutes each. Don't go deeper than needed to answer the audit questions.

### 3.1 Backend: data ingestion
- `src/axiom/ingest/pipeline.py` — what does the pipeline actually accept? What does it output?
- `src/axiom/ingest/broadcaster.py` — is this actually broadcasting to WebSocket?
- `src/axiom/sources/synthetic.py` and `live_synthetic.py` — fixture file or generated?
- Are there any **real** source connectors (Slack/GitHub/Linear/Notion) or only synthetic?
- `fixtures/synthetic_company.json` — how many entities, what shape, where loaded?

### 3.2 Backend: classification (OrganizerAgent)
- `src/axiom/organize/` — what's in there?
- README mentions a "Phase 5.7 hybrid cluster classifier" with optional Anthropic Haiku fallback. Does this exist? Is it wired?
- Does classification actually run on incoming entities? Or are entities pre-classified in the fixture?
- Is `composite_importance` computed by code, or hardcoded in fixture?

### 3.3 Backend: governance (AEGIS)
- `src/axiom/govern/` — what files? What do they do?
- README claims "signs every agent action with hybrid Ed25519 + ML-DSA-65 (FIPS 204) and enforces ALLOW / CORRECT / DENY / PAUSE."
- Is the signing real (cryptography library, real key pairs, real signatures)? Or scaffolded?
- Is the policy enforcement real (does it gate actions)? Or just emits decision events?
- `src/axiom/sign/` — actual signing? Test signatures? Verify the math is real.
- `src/axiom/policy/` — actual policy engine? What rules exist?

### 3.4 Backend: API endpoints
List **every** FastAPI route in `src/axiom/studio/server.py`. For each:
- Path, method, does it work
- Returns real data or canned?
- Used by frontend? (grep frontend code)
- `src/axiom/api/search.py` — keyword? embedding? LLM? What does it actually do?

### 3.5 Backend: WebSocket
- `/ws/brain` — what events does it emit?
- Are these events triggered by real activity, or by `LiveSyntheticSource` running on a timer?
- If synthetic, what's the rate?

### 3.6 Backend: persistence
- `alembic/versions/` — what migrations exist?
- `src/axiom/storage/` — actual SQLAlchemy ORM? Real CRUD?
- `axiom.db` — does it have real schema + data?

### 3.7 Backend: skills + MCP
- `src/axiom/skills/` — what's actually there?
- `src/axiom/mcp/` — is there an actual MCP server, or just interfaces?
- README claims "Skills exposed via MCP (12)". Are 12 skills real?

### 3.8 Frontend: scene rendering (Brain.tsx)
- Does it bootstrap from real backend at `127.0.0.1:8000/api/entities` and `/api/edges`? Confirm.
- WebSocket `/ws/brain` — does it receive real events? (Watch the network tab while running)
- Is the cluster reframe doing what it claims (8 super-clusters)?
- Are intra-cluster web lines, particle conduits, satellite packing all rendering from real entity counts?

### 3.9 Frontend: chrome
For each component, mark FUNCTIONAL / STUB / DECORATIVE:
- `NavRail` (Brain / Explore / Agents / Insights / Governance / Settings / Account)
- `TopHeader` (AXIOM + LIVE pill)
- `BrainHealthCard` (Entities, Relationships, Events/min, Classified, Health)
- `QueryBar` (input, ⌘K, send button, prompt chips)
- `EdgeLegend` (color-coded categories)
- `EntityInspector` (Overview, Connections, Lineage, Activity tabs)
- `StatusFooter` (Graph / Flow / Governance / Timeline / Search / Receipts / Agent Console tabs)
- `CommandPalette` (⌘K dialog)

### 3.10 Frontend: dead/legacy code
- `src/components/company-brain/` — is this used by App.tsx?
- Any other unused components?
- `frontend/src/components/CompanyBrainPage.tsx` and `CompanyBrainGraph*.tsx` — alive or dead?

### 3.11 Tests
- Run `cd frontend && npm test -- --run --reporter=basic` and report counts
- Run `pytest` in repo root if a Python test suite exists; report counts
- Are the tests testing real behavior or trivial assertions?
- The 5 failing CompanyBrainGraph.interaction tests — what are they actually testing? Should they be deleted?

### 3.12 Production-readiness
- Is there a Dockerfile or deployment config?
- Is `axiomctrl.com` (claimed hosted demo per README) live? Try `curl -I https://axiomctrl.com`
- Are there any obviously broken hardcoded localhost references that would fail in production?
- Are secrets handled correctly? (no API keys in repo)

---

## §4 — REPORT FORMAT

Write `docs/AXIOM_AUDIT_REPORT.md` with these sections:

```
# AXIOM AUDIT REPORT
Date: [today]
Auditor: Claude Code
HEAD commit: [hash]

## TL;DR (5 sentences max)
- What % of the system is real working code
- What % is scaffold (stubs, interfaces, no implementation)
- What % is dead/orphaned code
- The 3 most important truths the owner needs to know
- The 1 thing that would surprise them most

## What's REAL (works end-to-end)
[bullet list with file references]

## What's SCAFFOLDED (exists but doesn't do what the name suggests)
[bullet list with file references and what it actually does vs. claims]

## What's DEAD (orphaned/unused/never wired)
[bullet list — candidates for deletion]

## What's MISLEADING (README or UI claims something the code doesn't deliver)
[bullet list — these are the credibility risks if a YC reviewer reads the README and runs the code]

## Subsystem-by-subsystem detail
### Ingestion
### Classification
### Governance
### API
### WebSocket
### Persistence
### Skills/MCP
### Frontend rendering
### Frontend chrome (with FUNCTIONAL/STUB/DECORATIVE tag per component)
### Tests
### Deployment

## YC submission risk assessment
- If a YC reviewer reads the README + clones the repo + runs `npm install && npm run dev` + the backend, what will they see vs. what does the README claim?
- What are the 3 specific things they could call out as "this doesn't actually work"?
- Recommendation: ship as-is, polish first, or rebuild specific parts

## Recommended next steps (prioritized for time-to-YC)
- 1-hour fixes (quick credibility wins)
- 1-day fixes (real product progress)
- 1-week fixes (substantial new capability)
- Things to NOT do (scope traps)
```

---

## §5 — CONSTRAINTS

- **Read-only.** Do not modify any code, do not run any code that writes to disk, do not commit anything.
- You may run the frontend dev server and backend, browse the running app, watch network traffic, exec curl commands. These are read operations.
- You may NOT call Anthropic API or any LLM — the audit is purely static + runtime observation.
- Be specific. "The signing module is scaffolded" is useless. "src/axiom/sign/ed25519.py:42 calls a function that returns a hardcoded test signature; no real keypair is loaded; line 67 has TODO" is useful.
- Be brutal. The owner needs to know what's real, not feel good about what's there. Frame as a friend giving the owner a heads-up before submission, not as a marketing assessment.
- One report. Don't write multiple files. Don't get distracted into refactoring suggestions beyond the recommended next steps section.
- Time budget: 60–90 minutes total. If a subsystem is taking longer, summarize what you found and move on.

When done, the file `docs/AXIOM_AUDIT_REPORT.md` should exist and you should output a summary stating it's complete.

Begin.
