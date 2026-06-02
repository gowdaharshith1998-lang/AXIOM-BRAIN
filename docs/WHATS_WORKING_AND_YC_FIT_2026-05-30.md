# AXIOM-BRAIN — Honest Engineering Status Report

## 1. Does it run?

**Yes — both halves run clean.** **Backend:** `pytest` is **602/603 green** (~26s); `create_app` imports cleanly and a live uvicorn boot comes up in ~1s, enforces JWT auth (401 unauth → 200 after login), and serves `/api/health`, `/api/graph/*`, `/api/connectors` on a real (empty) SQLite DB. One real failing test: Linear first-sync ingests 0 entities. **Frontend:** `vitest` is **390 passed / 18 skipped, 0 failed** (~9s) and `tsc -b && vite build` produces a production `dist/` (305 kB gzip JS). Caveat: the *documented* server entrypoint `uvicorn axiom.studio.server:app --factory` is broken (no module-level `app`); the working entrypoint is `axiom serve`.

---

## 2. ✅ What works (real, end-to-end)

| Subsystem | What's proven | On real data? |
|---|---|---|
| **Ingest pipeline + broadcaster + WebSocket** (`ingest/pipeline.py`, `ingest/broadcaster.py`, `/ws/brain`) | Persists entities/edges to SQLite, monotonic sequenced envelopes, `?since=` replay, auth-gated socket. Tests pass. | Source-agnostic transport — carries both synthetic and real envelopes |
| **Self-organizing engine** (`organize/`) — keyword classifier, OrganizerAgent 4 loops, CentralityScorer (networkx PageRank+degree+recency), 7 fixed cluster lobes | 47 tests pass; real networkx graph algorithms; boot backfill + periodic loops wired into lifespan | Runs on any DB rows; demonstrated on synthetic fixtures |
| **Retrieval engine** (`retrieval/search.py`, `graph_rank.py`) — lexical, semantic-cosine, 1-hop graph, **genuine RRF fusion (k=60)**, **networkx Personalized PageRank** | RRF/PPR/modes/filters all tested; wired into Studio + MCP + brain_ask | Lexical+graph legs real; queries real ORM tables |
| **MCP server** (`mcp/server.py`) — 16 FastMCP tools over stdio (`axiom mcp-serve`) | 70/71 tests pass; read/walk/traverse return real graph data; passport-gating + signed-receipt writes proven | Reads real `Entity`/`Edge`; default DB |
| **ed25519 receipt signing + pre-execution policy gate** (`sign/ed25519_signer.py`, `govern/receipts.py`, `govern/verify.py`, `connectors/writer.py`) | Real AES-key crypto, sha256 hash-chain, signature verification via API, policy DENY raises `ConnectorWriteBlocked` *before* the vendor call | Real crypto over real DB rows |
| **Policy DSL + RealPolicyEvaluator** (`policy/dsl.py`, `predicates.py`, `evaluator.py`) | Real tokenizer/parser/AST, 10 predicates (PII+Luhn, watchdog DB lookup, rate-limit), first-match engine over real YAML rules | Evaluates real context objects |
| **Secrets vault** (`vault/`, `govern/llm_keys.py`) — **the most production-real subsystem** | Real Fernet (AES-128-CBC+HMAC), fail-closed, ciphertext-only at rest, matching Alembic migrations, full OAuth→encrypt→store→read-back loop wired for all 5 vendors, real HTTPS key-verification. **43 tests green, crypto not mocked** | Real ciphertext, real SQLite |
| **SkillFiles** (`skills/skill_file_*.py`) — deterministic YAML workflow engine | **19 tests pass**; executes 5 step types against real storage + governance (fetch/write entities, chain receipts, DSL conditions, approval creation); frontend block-builder round-trips | Executes against real SQLite; **no LLM needed** |
| **GitHub + Gmail connectors** (`connectors/github`, `connectors/gmail`) | Per the trace, **actually ingested a real account once** — DB residue showed 112 GitHub + 116 Gmail entities, real `client_id`s, `repo_has_issue`/`repo_has_pull_request` edges | **REAL (historically) — but see §4: that DB is now empty** |
| **Frontend SPA + clients** (`App.tsx` router, ~15 pages, 55 lib modules) | Every frontend fetch maps to a real backend route (102 routes); build + 390 tests pass; WS bridge with seq-dedup/replay | Real REST wiring |

---

## 3. 🟡 Partial / synthetic-only (works, with caveats)

- **All 5 connectors are mock-tested, not proven-on-real-APIs.** Every connector unit/e2e test mocks vendor HTTP via the `responses` library — **88/89 pass under mocks**. OAuth code-exchange, per-vendor webhook HMAC/JWT verification, paginated/GraphQL clients, and Fernet-vaulted tokens are all genuinely coded. But the only real-API exercise was a manual one-off (GitHub+Gmail); **Linear/Slack/Notion never touched a real account** and have zero data in the DB. There is **no repeatable live-API integration test**.
- **Ask-the-Brain RAG** (`api/brain_ask.py`, `POST /api/brain/ask`): retrieval half is real and tested (8 tests); citation building, grounded prompt, error mapping all concrete. But **the LLM answer is never exercised even mocked at the HTTP layer** — every test injects a stub completer; there is no `test_llm_chat.py`. Returns **409 with no provider key**. The real `chat_complete` httpx client (`providers/llm_chat.py`) is dead-code from a test perspective.
- **Semantic retrieval leg**: uses `DeterministicEmbeddingProvider` (64-dim sha256 hash vectors) everywhere under pytest and whenever no OpenAI key is present. The real `OpenAIEmbeddingProvider` is coded but bypassed — **semantic-similarity quality is never proven on real embeddings**.
- **Classifier LLM Tier-2 (Anthropic Haiku)**: real code, but the **anthropic SDK isn't installed** and no live key is wired — silently degrades to keyword-only; all LLM tests use a `_FakeClient`.
- **3D brain visual** (`Brain.tsx:101-116`): **synthesizes placeholder nodes by design** ("Visual placeholder synthesized from aggregate cluster metadata") and pads each cluster to a visual cap — the rendered graph is always partly fabricated. The "live" Poisson motion only runs with `--live` and is synthetic.
- **Watchdog detectors** (7 rules R1-R7, `govern/watchdog_rules.py`): real logic incl. cosine-outlier math, but **tuned to demo cluster-ids/data shapes** and never proven firing on real connector data.
- **MCP auth on real data**: defaults to **DENY** unless `AXIOM_MCP_ALLOW_SYSTEM_PASSPORT=1` or a real passport token — and **real external-agent passports are never provisioned** (only the hardcoded `demo_passport`).

---

## 4. 🔴 Not working / stubbed / missing

- **The committed `axiom.db` is now EMPTY** (0 entities, 0 edges, 0 connector_states). The 73MB DB that held the real GitHub+Gmail proof is **gone from the shipped artifact** — the only evidence of real ingestion is historical residue, not present in the repo you'd clone.
- **Linear first-sync is broken** — returns HTTP 200 but **ingests 0 entities** (`tests/test_connectors_e2e_smoke.py:259` → `assert 0 >= 1`). Fails in isolation, so it's a genuine sync→ingest mapping defect, not test pollution.
- **`query_brain` has dead code** — returns at `mcp/server.py:1107`, leaving the FTS neighbor-expansion block (1109-1186) unreachable; this is the single failing MCP test.
- **"Self-improving" pillar — MISSING entirely.** No learning, feedback, quality metric, or graph-growth tracking. Aspirational language with zero implementation.
- **ML-DSA-65 post-quantum signing — STUBBED.** Exists only as a type literal + unused field on an abstract `Signer` raising `NotImplementedError('Phase 10')`.
- **Broken documented entrypoint** — `uvicorn axiom.studio.server:app --factory` (README:63 / PRODUCTION.md:63) has no module-level `app`.
- **Empty-string signatures on watchdog/approval receipts** — those receipts are hash-chained but would **FAIL signature verification**.
- **Fail-OPEN policy fallback** — if real policies fail to load, it silently falls back to `DemoPolicyEvaluator(deny_rate=0)` which allows nearly everything.
- **Productization gaps**: no Dockerfile (despite PRODUCTION.md referencing one); committed `.venv` is a fake symlink-to-system-python with no site-packages; CORS hardcoded to `localhost:5173`; single-workspace only (no multi-tenancy).
- **Hidden UI**: Governance/Approvals/Schedules/Triggers/Runtime pages exist with working backends but are deliberately commented out (`HIDDEN-V2`, commit a2023c1) — dead in the shipped build. Sidebar account chrome is hardcoded ("Axiom Corp." / "Enterprise Plan").
- **Connector registry is vestigial** — `registry.py` factories all return `None`; real sync bypasses it. `connector_events` table has 0 rows (webhook/poll increments never persisted).

---

## 5. Is it the "company brain" YC described?

**The intended vision** (README.md:3): *"A living knowledge graph that ingests your company's tools, organizes itself, and lets humans and AI agents query institutional memory — under cryptographic governance."* The YC pitch (docs/AXIOM_COMPANY_BRAIN_AUDIT.md:15): *"AXIOM is the company brain: it ingests everything, organizes itself, and becomes the single place humans and agents go to understand the company — under cryptographic governance so you can trust what the agents do."* Four pillars: **KNOW, ORGANIZE, ANSWER, GOVERN**, plus a "self-improving" promise.

**Verdict: Not yet — it's an impressively engineered *demo of the architecture*, not a brain running on a real company's live tools. Score: 4.5/10.**

**Demo vs. real truth:** The engineering is well above demo-ware — the ingest/organize/retrieve/MCP/governance/vault subsystems are real concrete code (the `NotImplementedError` sites are all abstract interface bases, never the hot path), 602/603 backend + 390 frontend tests pass, and the ed25519 + Fernet crypto is genuine. But **every load-bearing "real company brain" claim resolves to synthetic or unproven**: the curated "company" (people/decisions/tickets) is a 100-entity hand-authored fixture; the "live" motion is a synthetic Poisson emitter; the LLM answer/classifier paths are stubbed (no key, no SDK); governance has only ever signed `demo_flag=True` actions under a hardcoded `demo_passport`. To the repo's credit, its own internal audit reaches the identical conclusion (AXIOM_COMPANY_BRAIN_AUDIT.md:61): *"a sophisticated demo on mostly synthetic data, not yet a company brain running on a real org's live tools."*

**Biggest gaps between what exists and what's pitched:**
1. **KNOW** — connectors are mock-tested only; 3/5 never touched a real account; Linear sync is broken; and the real-data proof DB is now empty.
2. **ANSWER** — the *self-declared headline* (Ask-the-Brain) has never produced a real grounded answer; semantic retrieval runs on hash vectors, not real embeddings.
3. **ORGANIZE** — edge proposal is one hardcoded heuristic (`same_cluster_related`), not semantic reasoning; the LLM classifier tier is dead.
4. **GOVERN** — real crypto, but only ever applied to synthetic demo actions; some receipts carry empty signatures; fail-OPEN fallback.
5. **Self-improving** — pitched pillar with **zero** implementation.

Per-pillar honest grading: roughly **"demo-done" on most pillars and "real-done" on none of the headline ones.** The one pillar that *is* essentially production-real is the **secrets vault** (genuinely solid Fernet + OAuth round-trip).

---

## 6. The bottom line

You have a genuinely impressive, well-tested **engine** for a company brain — the hard architectural plumbing (ingest, self-organization, RRF/PageRank retrieval, a 16-tool MCP server, real ed25519+policy governance, a production-grade vault) is real and 992 tests pass. What you do **not** have is a brain proven on a real company: the LLM answer/classify paths are stubbed (wire a real key + add an HTTP-level test), 3 of 5 connectors have never seen a real account and Linear's sync is broken (`tests/test_connectors_e2e_smoke.py:259`), and the one real-data datapoint you once had is gone because the committed `axiom.db` is now empty. The fastest path to matching the pitch: (1) wire and prove the LLM paths and real OpenAI embeddings on a live key, (2) fix Linear and prove all five connectors on real accounts with a repeatable integration test, then re-seed real data, and (3) retire the demo-governance scaffolding (`demo_passport`, `demo_flag=True` defaults, empty-string signatures, fail-OPEN fallback) so the real crypto governs real actions. Do those and the 4.5 becomes a defensible "real."
