# AXIOM-BRAIN Production-Readiness Report

## 1. Verdict

AXIOM-BRAIN is a feature-rich, architecturally ambitious system whose **core enforcement and persistence layers are not yet safe to run as a production service** — it is roughly **4–6 weeks of focused work away** from a defensible single-tenant production deploy, more for multi-user. The single biggest theme is **"fail-open by default, single-process by design"**: the security/governance controls that are the product's headline value (passport authorization, the signed receipt chain, policy enforcement) all default to permissive or trivially-bypassable states, while the runtime (default-rollback SQLite with foreign keys off, one event loop doing blocking I/O, no backups, no observability, no deploy artifact) is built for a demo on localhost, not for concurrent real traffic. Encouragingly, the *primitives* are largely correct — the HTTP/WS auth middleware, webhook HMAC verification, OAuth CSRF state, parameterized SQL, and Ed25519 signing all work as intended; the failures are in **defaults, wiring, and operational scaffolding**, which are concentrated and fixable rather than diffuse rot.

---

## 2. P0 — Blockers (must fix before ANY deploy)

### P0-1. Hardcoded god-token `demo_passport` is a remotely-exploitable auth backdoor — Effort: M
*(merges AUTHZ-001, GOV-PASS-002)*
- **Problem:** `src/axiom/govern/passports.py` defines `SYSTEM_PASSPORT_TOKEN = "demo_passport"` and `ensure_system_passport()` unconditionally mints a wildcard (`*/*/*`), 365-day passport whose credential is `sha256("demo_passport")`. `AxiomMCPService.__init__` (`src/axiom/mcp/server.py:203`) calls this on every boot with no env guard. `verify_passport()` accepts any token matching a stored hash with no production gate, and `check_scope()` honors `*`. The token is reachable by an **unauthenticated external caller** via `POST /api/mcp/invoke` (`src/axiom/studio/routes/mcp.py`), which forwards `passport_token` to `run_tool` with no auth dependency, behind `allow_origins=["*"]`.
- **Why it blocks:** A publicly-known constant grants full read/write/skill-invoke authority over the entire brain from any browser origin the moment the server boots in any environment. CWE-798 + CWE-306.
- **Fix:** Never persist a static-token wildcard passport. Gate `ensure_system_passport` behind an explicit `AXIOM_DEMO` flag AND `AXIOM_ENV != production` at the `mcp/server.py:203` call site; when a bootstrap agent is genuinely needed, generate a random `secrets.token_urlsafe` bearer, store only its hash in the vault, scope it minimally with a short TTL. Explicitly reject the literal `demo_passport` in `verify_passport` when `_is_production()`. Apply the existing `_reject_wildcard_passport_scopes` logic to internal issuance too. Add a regression test asserting `demo_passport` returns `invalid_or_missing_passport` in production.

### P0-2. Studio HTTP auth is fail-OPEN by default — Effort: S
*(GOV-AUTH-001, reinforced by FE-NO-CLIENT-AUTH context)*
- **Problem:** `src/axiom/studio/auth.py:29-34` — `auth_required()` is **False** unless `AXIOM_API_TOKEN` is set OR `AXIOM_AUTH_REQUIRED` is truthy OR `AXIOM_ENV=production`. A deploy that omits the token and doesn't set `AXIOM_ENV=production` serves every non-exempt route (mint/revoke passports, kill-switch, approvals, receipt log, `/api/brain/ask`) with **no authentication**.
- **Why it blocks:** The governance control plane and the company brain are exposed unauthenticated by configuration default. Localhost CORS does not stop server-to-server/non-browser requests.
- **Fix:** Fail closed: default `auth_required()` to True; require an explicit `AXIOM_AUTH_DISABLED=1` only for local dev. Wire `auth_is_misconfigured()` (already exists) into a hard startup failure (see P0-3). This is also the precondition for the frontend auth model (FE-NO-CLIENT-AUTH) — once auth is mandatory, the SPA must attach credentials.

### P0-3. App does not fail fast on missing/invalid VAULT_KEY or API_TOKEN at boot — Effort: S
*(STARTUP-NO-FAILFAST; the enforcement half of P0-2)*
- **Problem:** `src/axiom/env.py:42-57` only logs a warning on a missing/malformed `AXIOM_VAULT_KEY`; `create_app` (`server.py:474`) performs no config validation and never raises. A production server with no token boots, binds, and returns 503 on every protected route — a silent misconfig discovered only by users hitting errors.
- **Why it blocks:** Misconfiguration is invisible until traffic arrives, and the misconfigured instance still serves callbacks/webhooks. It is the operational guarantee behind P0-2.
- **Fix:** In `create_app`, before returning the app: if production and `configured_api_token()` is None → `raise SystemExit`; if `AXIOM_VAULT_KEY` is present but Fernet-invalid → `raise SystemExit`. Bind only to loopback if auth is required but unconfigured.

### P0-4. Live OpenAI key + Fernet vault master key sit in plaintext `.env` — Effort: S
*(SEC-LIVE-OPENAI-KEY-IN-ENV)*
- **Problem:** `/home/harsh/AXIOM-BRAIN/.env` line 35 contains a live `sk-proj-...` OpenAI key; line 27 contains the real `AXIOM_VAULT_KEY` Fernet master key that decrypts **all** vault-stored connector OAuth tokens and provider keys. (Git history is clean — this is on-disk exposure, not a leak.)
- **Why it blocks:** Live key beside the vault master key = one screen-share/backup/paste/mis-add from full SaaS lateral compromise (every GitHub/Linear/Slack/Notion/Gmail credential). The key is now quoted in audit artifacts and must be treated as compromised.
- **Fix:** (1) Revoke/rotate the `sk-proj` key **now**. (2) Remove the duplicate placeholder line 34. (3) In production inject `AXIOM_VAULT_KEY` from a secrets manager/KMS/systemd `EnvironmentFile`, never beside live keys; re-encrypt the vault if exposure is suspected. (4) Store provider keys in the encrypted vault via `POST /api/internal/llm-keys`, not `.env`. (5) Add a pre-commit secret scanner (gitleaks/trufflehog).

### P0-5. SQLite runs with no WAL, busy_timeout=0, and foreign_keys=0 — Effort: M
*(DB-001; root cause shared with DEP-03, SQLITE-ENGINE-NO-THREAD-CONFIG, DB-007)*
- **Problem:** Runtime probes confirm `journal_mode=delete`, `busy_timeout=0`, `foreign_keys=0`. `src/axiom/storage/db.py` sets no PRAGMAs anywhere in `src/`. The organizer runs as a **separate writer process** (`cli.py:19`) against the same file. With rollback journaling + busy_timeout=0, a second writer hitting the EXCLUSIVE lock fails immediately with `database is locked`; with FKs off, all 8 ForeignKey constraints are silently unenforced (orphaned edges/receipts/skill_runs).
- **Why it blocks:** Intermittent 500s under any concurrent writer **and** silent data-integrity corruption — both unacceptable in production.
- **Fix:** Register a SQLAlchemy `event.listens_for(engine, "connect")` handler in `_build_engine` running `PRAGMA journal_mode=WAL; busy_timeout=5000; synchronous=NORMAL; foreign_keys=ON` for sqlite URLs. Serialize the organizer/ingest writers behind one write connection. Route the ad-hoc engines (`cli.py:19`, `skill_file_runner.py:467`) through the central factory so the config applies uniformly. Plan a Postgres migration for the websocket+sync+organizer workload.

### P0-6. No inbound rate limit / quota / cost cap on the paid Ask-the-Brain LLM endpoint — Effort: M
*(OBS-01-NO-RATE-LIMIT-LLM)*
- **Problem:** The only middleware on the app is CORS + the auth gate. `POST /api/brain/ask` (`brain_ask_api.py:40`) does Pydantic validation only, then makes a real paid LLM call plus DB-heavy hybrid retrieval. No per-IP/per-token limit, no concurrency cap, no daily cost ceiling. With auth opt-in (P0-2), this is anonymous by default.
- **Why it blocks:** One buggy or malicious client can run up an unbounded LLM bill and saturate the single SQLite-backed process — direct financial loss + DoS.
- **Fix:** Add a rate-limit dependency (note: `slowapi` is **not** currently installed — add it or `limits`/a reverse-proxy quota). Enforce per-token + per-IP limits (e.g. 10/min, burst 3) on `/api/brain/ask` and embedding routes, a per-key concurrency semaphore, and a configurable daily token/cost cap that fails closed (429 + Retry-After). Track cumulative spend per provider key. Pairs with P0-2 (fail-closed auth).

---

## 3. P1 — Required before real users

### P1-1. Policy engine fails OPEN to allow-all on any load error — Effort: S
*(GOV-POL-006)* `get_policy_evaluator` (`policy_evaluator.py:98-112`) returns `DemoPolicyEvaluator(deny_rate=0)` on **any** loader exception or empty ruleset — allowing everything except a single hardcoded `billing_payments+write` rule, while still emitting `decision="allow"` receipts that look governed. **Fix:** in production, deny-by-default (or refuse to start) when policies fail to load or are empty; reserve the demo evaluator for an explicit `AXIOM_DEMO` flag; surface "policy load failed / demo mode active" on a health endpoint. *(Borderline P0 if policy is the sole control in front of real mutations.)*

### P1-2. Signing key is auto-generated unencrypted and self-verified (no real non-repudiation) — Effort: M
*(GOV-KEY-003)* `ed25519_signer.py` writes the private key to `~/.axiom/signing_key.pem` with `NoEncryption()`, silently auto-generates it when absent, and both `verify.py:37` and `passports.py:92` verify against that same local key (circular). **Fix:** load the key from the Fernet vault/KMS; in production refuse to start if absent rather than auto-generating; pin and publish a stable trust-root pubkey and verify against it; share one key across workers with rotation-with-overlap.

### P1-3. Receipt chain is not tamper-evident against a DB writer — Effort: L
*(merges GOV-SIG-004, GOV-CHAIN-005)* The Ed25519 signature is computed over a canonical payload that **excludes `prev_hash`** (`receipts.py:125-131`), so a signed receipt can be relocated in the chain and still verify; chain integrity rests only on a fully re-derivable SHA-256 prev/this linkage with no external anchor and no DB immutability. Combined with P1-2, a holder of the on-disk key can rewrite history self-consistently. **Fix:** sign over a single canonical representation that includes `prev_hash` (or sign `this_hash` itself); unify the two canonicalizers; anchor the chain head to an append-only external store and verify backward from the latest anchor; enforce row immutability via SQLite triggers; add a test that relocates a signed receipt and asserts verification fails.

### P1-4. Webhook/event ingest has no idempotency — replay duplicates data and inflates metrics — Effort: M
*(merges DEDUP-NO-UNIQUE-CONSTRAINT, DB-005)* `ConnectorEventRow` has only **plain** indexes on `(vendor, external_id)` — no UniqueConstraint — and every webhook route (GitHub/Linear/Slack/Gmail/Notion) blind-inserts then re-applies to the brain with no existence check. At-least-once delivery + provider retries therefore duplicate event rows, double-count the activity metric (`server.py:2439`), and re-apply to the brain. **Fix:** add `UniqueConstraint("vendor", "external_id")` + Alembic migration; wrap each insert in a `begin_nested()` SAVEPOINT catching `IntegrityError` as a benign duplicate and skipping the brain re-apply; store NULL (not `""`) for missing external_ids; collapse pre-existing dupes before applying the index.

### P1-5. Connector sync runs blocking `requests` HTTP on the event loop — Effort: M
*(BLOCKING-ASYNC-SYNC)* `sync_github/linear/slack/notion/gmail` (`sync_runner.py`) iterate synchronous `requests` calls with zero `to_thread`/`run_in_executor`, awaited directly from request handlers and the background `connector_sync_loop`. A slow upstream wedges the whole single-process backend — request queue, broadcaster/WS, and the 15s health loop all stall. **Fix:** wrap each syncer body in `asyncio.to_thread(...)` or migrate the fetchers to the already-declared `httpx.AsyncClient`; add a concurrency cap.

### P1-6. Retrieval loads the entire entities table into Python per search — Effort: L
*(DB-003)* `retrieval/search.py` issues unbounded `select(Entity)` and runs full-Python cosine/keyword scoring before the `[:limit]` slice (live: 6,432 entities, 127k edges). Every brain query / MCP `query_brain` / studio search pulls the full set into memory while holding a read lock, so p99 grows linearly and compounds the DB-001 lock contention. **Fix:** push filtering/ranking into the DB (FTS5 for keyword, a real ANN index — `ruvector.db` already ships — for vectors), always apply a hard LIMIT to the candidate scan, add a perf test bounding candidate-set size.

### P1-7. No backup/restore strategy for the 73MB DB holding the receipt chain — Effort: M
*(DB-004)* `axiom.db` (~73MB, untracked) holds the hash-chained audit log + the full graph, with **zero** backup/restore/integrity guidance in `PRODUCTION.md` and no WAL (so a crash mid-write risks corruption). **Fix:** enable WAL (P0-5), then add Litestream continuous replication or a cron `.backup` with offsite copy + periodic `PRAGMA integrity_check`; document RPO/RTO and a tested restore runbook.

### P1-8. No deployment artifact: Dockerfile/compose/IaC absent despite documented `docker build` — Effort: L
*(DEP-01; intertwined with DEP-06, DEP-08)* No Dockerfile/.dockerignore/compose/IaC on disk, in the index, or in history, yet `PRODUCTION.md:39-41` documents `docker build`/`docker run`. The documented container path fails immediately; the single-origin SPA claim also fails because `frontend/dist` is gitignored and never assembled into a deploy artifact (DEP-06). **Fix:** add a multi-stage Dockerfile (node build → `frontend/dist`; python runtime → uvicorn), a `.dockerignore` (excluding `.venv`, `node_modules`, `*.db`, `.git`, `AXIOM-BRAIN/`), a compose file with a named volume for the SQLite DB, and one IaC target. Or, if Docker is not intended, delete the Container section and rewrite `PRODUCTION.md` around the working `uvicorn ... --factory` launch (DEP-08).

### P1-9. Dev environment + CI are unrunnable/stale; builds are non-reproducible — Effort: M
*(merges VENV-MISSING-DEV-TOOLING, CI-STALE-SKELETON, DEP-001, DEP-05/lockfile)* The local `.venv` is Python 3.14.4 (CI targets 3.13) with no dev tooling installed (`pytest`/`mypy`/`ruff`/`responses` absent) — the 581-test suite cannot be proven green. `ci.yml` is a phase-1 skeleton last touched when `tests/` had 3 files: `pytest -xvs` (fail-fast, no junit/coverage/timeout) and `npm install` (not `npm ci`). 12 runtime deps are unpinned and CI installs editable, ignoring the committed `uv.lock`. **Fix:** recreate the venv on 3.13 with `pip install -e .[dev]`, add a `.python-version`; rewrite CI to `pytest -q --maxfail=5 --junitxml --cov`, switch to `uv sync --frozen` and `npm ci`, add caching + per-job timeouts + a `uv lock --check` gate; add upper bounds to framework/crypto deps.

### P1-10. No CD / release automation — Effort: M
*(DEP-05/ci-cd)* No deploy workflow: no image build/push, no `alembic upgrade head` on deploy, no health-gated rollout, no rollback. Combined with DB-002 (no boot-time migration), the 15 migrations must be applied by hand. **Fix:** add a tag/main-triggered deploy workflow that builds+pushes the image (after P1-8), runs `alembic upgrade head`, deploys, then probes `/api/health` as a promotion gate.

### P1-11. Competing schema sources, no boot-time migration, no drift check — Effort: M
*(DB-002)* Alembic (15 revisions, live stamp `b3c4d5e6f7a8`) coexists with `Base.metadata.create_all` (`skill_file_runner.py:468`) and ad-hoc `create_engine` calls; `server.py` has no lifespan/startup migration hook; a second empty `migrations/` tree (with a working `env.py`) invites revisions in the wrong place. **Fix:** make Alembic the single source of truth — remove `create_all`, route ad-hoc engines through the central factory, run `alembic upgrade head` at deploy, delete the unused `migrations/` tree, add a CI `alembic upgrade head && alembic check` step.

### P1-12. No metrics, no error tracking, shallow health check — Effort: M (combined)
*(merges OBS-02, OBS-03, OBS-04 / DEP-07)* No Prometheus/OTel/StatsD export anywhere; no Sentry (exceptions only hit stdout, with many broad `except Exception` swallowers); the sole `/api/health` (`server.py:796-803`) is a static dict that never touches the DB, vault, or background tasks (whose handles already sit on `app.state`). **Fix:** add `prometheus-client` + `/metrics` (request RED metrics, LLM call/token/cost counters, retrieval/ingest latency, per-task alive gauge); integrate `sentry-sdk` with `capture_exception` in the broad-except blocks; add `/livez` and `/readyz` (run `SELECT 1`, check `vault_unlocked`, verify each `app.state.*_task` is not `done()`-with-exception) and point the LB at `/readyz`.

### P1-13. Non-Gmail connectors never refresh OAuth tokens — Effort: M
*(NON-GMAIL-NO-TOKEN-REFRESH)* `github/slack/linear/notion` `refresh()` are no-ops; Linear stores a `refresh_token` it never uses; and `connector_token_state` never calls `oauth.refresh()`, so even Gmail's working refresh is not wired into sync. Linear sync silently dies once its access token expires, with no "reauth required" status. **Fix:** wire `connector_token_state` to refresh when expiry is near, implement Linear (and Slack rotation) refresh, persist updated tokens to the vault, and surface a `reauth_required` status in the UI on failure.

### P1-14. WebSocket URL hardcodes `:8000` — live updates die behind a reverse proxy — Effort: S
*(FE-WS-PORT-8000)* `App.tsx:222`, `Brain.tsx:309`, `PassportsPage.tsx:58` all build `wss://${hostname}:8000/ws/brain` (port-less host + literal :8000), while HTTP `/api` is correctly relative. Behind nginx/Cloudflare on 443, the WS never connects and all real-time graph/event streaming silently fails. **Fix:** use `window.location.host` (includes the port) via a single `wsUrl()` helper; extend `relative-api-urls.test.ts` to assert no `:8000` literal in any `/ws` URL.

### P1-15. SPA has no mechanism to send auth credentials — Effort: M
*(FE-NO-CLIENT-AUTH)* Every `*Client.ts` wrapper and the WS use bare `fetch`/`new WebSocket` with no `Authorization` header and no `credentials: "include"`. Once auth is mandatory (P0-2), the UI is non-functional in prod. **Fix:** decide the auth model — an HttpOnly session cookie set by the reverse proxy is safest (add `credentials: "include"` to the shared `request()` wrapper; WS inherits the cookie on a same-origin connect, which requires the P1-14 fix). If token-based, keep it in memory (not localStorage).

### P1-16. Nested duplicate repo + committed binary DB corrupt the next bulk `git add` — Effort: S
*(merges HYG-01, SEC-NESTED-DUPLICATE-REPO, and ruvector.db across SEC-RUVECTOR-DB-COMMITTED/DEP-02/DB-007/HYG-02)* A full 9.5MB second checkout with its own `.git` sits at `AXIOM-BRAIN/AXIOM-BRAIN/`, untracked **and** un-gitignored — `git add -A` from root would stage it as a broken embedded gitlink (git itself warns). Separately, the 1.5MB binary `ruvector.db` is committed and not ignored (asymmetric with the correctly-ignored `axiom.db`). **Fix:** verify the nested copy has no unique work (HEAD == root `a2023c1`), `rm -rf` it, and add anchored `/AXIOM-BRAIN/` to `.gitignore`; `git rm --cached ruvector.db` and add `*.db`/`ruvector.db` to `.gitignore`, regenerating it at runtime.

---

## 4. P2 — Should fix soon

**Auth / access-control hardening**
- Vault unlock endpoint (`/api/internal/secrets/unlock`) has no rate-limit/lockout — brute-forceable by any token-holder; delete the dead duplicate handler (`server.py:205-210`). *(AUTHZ-003)*
- OAuth state is single-slot per connector, not session-bound — concurrent installs clobber each other; overloaded `install_state` column mixes nonce with lifecycle values. *(AUTHZ-004, OAUTH-STATE-SINGLE-SLOT-REUSE)*
- CORS is hardcoded to localhost and ignores config — drive `allow_origins` from `AXIOM_CORS_ORIGINS`, refuse `*`+credentials. *(AUTHZ-002, OBS-08, DEP-04)*
- Passport revocation/kill-switch not propagated across workers (60s verify cache); no global kill switch. *(GOV-PASS-008)*

**Governance enforcement gaps**
- CORRECT policy verdicts are advisory only — no server-side PII redaction or scope transformation; relies on a cooperative agent. *(GOV-CORRECT-009)*
- Approval expiry enforced only by an external sweep; `resume_token`/payload not bound at execution (replay/payload-swap window). *(GOV-APR-010)*
- ALLOW path is not transactional — effect commits in one session, receipt in another, so a crash leaves un-receipted state changes. *(GOV-TOCTOU-011)*
- MCP-path receipts carry discarded demo/merkle metadata; model default `signing_scheme='demo'` would hard-reject if any path bypassed `chain_insert_receipt`. *(GOV-DEMO-007)*

**Database / data integrity**
- `content_hash` dedup uses an unindexed JSON-path extraction → full scan per ingest; promote to an indexed first-class column. *(DB-006)*

**Connector resilience**
- No 429/Retry-After handling or retry/backoff on any vendor call — initial full syncs abort on rate-limit. *(NO-429-RETRY-BACKOFF)*
- Notion poller/fetchers read only the first page (no `has_more`/`next_cursor`) — silent partial sync. *(NOTION-POLLER-NO-PAGINATION)*

**Backend robustness**
- `cluster_health_loop` has no per-iteration try/except — one error permanently freezes `events_per_min` and cluster health events; add the guard + done-callbacks on all lifespan tasks. *(CLUSTER-HEALTH-LOOP-UNGUARDED)*
- Watchdog `_debounce_loop`/`_event_loop` unguarded — die on first error, silently disabling governance detection. *(WATCHDOG-INNER-LOOPS-UNGUARDED)*
- `/ws/brain` send loop has no `WebSocketDisconnect` handling — noisy unhandled exception per disconnect. *(WS-SEND-NO-DISCONNECT-HANDLING)*
- Add `check_same_thread=False`/explicit pool config (required before adding `to_thread` for P1-5). *(SQLITE-ENGINE-NO-THREAD-CONFIG)*

**SSRF / web hardening**
- No SSRF allowlist/private-IP block on outbound HTTP — add one shared guard for any config-driven URL (verify `skills/runner.py:64` and LLM/embeddings `base_url` first); hard-coded vendor hosts are fine. *(SSRF-OUTBOUND-HOST-ALLOWLIST-01)*

**Observability / ops**
- No request/correlation IDs; server module never configures logging (a bare ASGI launch may lose log levels) — add JSON logging + `X-Request-ID` middleware. *(OBS-05)*
- No inbound request body-size limit or server-layer request timeout — slowloris/oversized-payload risk. *(OBS-06)*
- No alerting hooks for failures/task crashes/cost thresholds. *(OBS-07)*

**Frontend**
- No React error boundary anywhere — a render throw white-screens the whole SPA; add a top-level boundary + one around `<Brain>`. *(FE-NO-ERROR-BOUNDARY)*
- No code-splitting — single ~1.13MB JS bundle; lazy-load routes + the Three.js subtree, add `manualChunks`. *(FE-NO-CODE-SPLITTING)*
- Most form inputs lack accessible names (3/38 labeled) — fails WCAG 4.1.2. *(FE-A11Y-INPUT-LABELS)*

**Supply chain**
- `pqcrypto` declared but imported nowhere (dead dep bundling 8–48MB native wheels; overstates "post-quantum"). *(DEP-002, GOV-PQ-013)*
- No Dependabot / pip-audit / npm audit / SBOM. *(DEP-003)*

**CI / test quality**
- `test_demo_simulator_disabled` uses a 9s wall-clock sleep — slow + flaky; assert task-never-created instead + add `pytest-timeout`. *(FLAKY-9S-SLEEP, CI-PYTEST-FAILFAST)*
- Coverage never measured despite `pytest-cov` declared — add `--cov` + baseline + `--cov-fail-under`. *(NO-COVERAGE-GATE)*
- No end-to-end test of ingest→broadcaster→websocket delivery (the core real-time path). *(NO-WS-E2E-FLOW-TEST)*
- Uncommitted edit to `settings-page.test.tsx` on main is unverified — run, decide intent, commit. *(FE-SETTINGS-TEST-UNCOMMITTED)*

**Repo hygiene / docs**
- `frontend/tsconfig.tsbuildinfo` committed and perpetually dirty — `git rm --cached` + ignore. *(HYG-03)*
- 9 stale dated AUDIT/BRIEF/REBUILD docs clutter `docs/` — move to `docs/archive/`. *(HYG-04)*
- README still markets the now-hidden governance UI as the flagship feature. *(HYG-05)*
- Backend TODO/stub markers in governance/MCP/connector paths — triage to implement or fail-loud (501). *(HYG-06)*

---

## 5. P3 — Polish / nice-to-have

- **Auth surface auditability:** delete duplicate/dead route handlers, split the 158KB `server.py` into modules, tighten `is_http_auth_exempt` to an exact allowlist + a test enumerating auth-exempt routes. *(AUTHZ-006)*
- **Fail-safe startup:** make `auth_is_misconfigured()` loud at startup (CRITICAL log / loopback-only bind). *(AUTHZ-005)* — largely absorbed by P0-3.
- **Webhook hardening:** uniform 401 regardless of config state (avoid enumeration), rate-limit + body caps; add Gmail Pub/Sub audience config check for diagnosability. *(WEBHOOK-DELIVERY..., GMAIL-WEBHOOK-NO-CONFIG-GUARD-CONSISTENCY)*
- **Verify-on-read write amplification:** `verify_passport` commits `presented_count` on every non-cached read — make best-effort/batched. *(GOV-PASS-012)*
- **Confirm-and-tidy items:** `_redirect_base()` returns a fixed/env base, not Host-derived (open-redirect check); webhook routes pass raw bytes to `verify()`; Gmail webhook broad-except returns definitive reject; narrow OAuth-exchange error logging to status+code with token redaction. *(OAUTH-REDIRECT-BASE-..., WEBHOOK-RAW-BODY-..., GMAIL-WEBHOOK-BROAD-EXCEPT, OAUTH-ERROR-RESPONSE-LOGGING)*
- **Fire-and-forget tasks:** store post-OAuth/initial-sync tasks on `app.state` with a done-callback; await/cancel on shutdown. *(POST-OAUTH-SYNC-FIRE-AND-FORGET)*
- **PQ scheme allow-list:** drop `'demo'`/`'hybrid'` from `VALID_SIGNING_SCHEMES` (no matching verification); change model default off `'demo'`. *(GOV-PQ-013, GOV-DEMO-007)*
- **Frontend:** strip `console.*` from prod bundle (`esbuild.drop`); validate API responses at the fetch boundary (zod) instead of `as T` casts. *(FE-CONSOLE-LOGS-PROD, FE-FETCH-UNVALIDATED-CAST)*
- **Packaging:** expose a module-level `app = create_app()` so standard ASGI tooling works without `--factory`. *(DEP-09)*
- **Dependency hygiene:** standardize on `httpx`, drop `requests`; pin `three`/`@types/three`/`three-nebula` together; document the `mcp==1.9.4` pin rationale. *(DEP-04, DEP-06, DEP-05)*
- **Tests/docs:** flesh out near-empty stub tests (esp. `test_migrations.py` upgrade/downgrade round-trip); add governance-integrity regression tests (relocated-receipt, fresh-host key, demo_passport inert, auth-required-by-default, fail-closed policy); add `CONTRIBUTING.md`/runbook + a `Makefile`. *(NEAR-EMPTY-STUB-TESTS, GOV-TEST-014, HYG-08, HYG-07)*
- **Secret-logging note:** document that `vault init` stdout contains a live secret; optionally write the key to a 0600 file instead. *(SEC-KEY-RESOLUTION-LOGGING)*

---

## 6. Suggested sequencing

**Week 1 — Stop the bleeding: security defaults & secrets** *(P0-1…P0-4, P1-1, P1-16)*
Rotate the OpenAI key immediately. Flip auth fail-closed (P0-2) + boot-time fail-fast (P0-3); kill the `demo_passport` backdoor (P0-1); move the vault key out of `.env` (P0-4); make policy fail-closed (P1-1); delete the nested repo + uncommit binary DBs (P1-16). All small/medium, mostly independent — parallelize across two engineers (one on auth/passport/policy, one on secrets/hygiene). **Gate: nothing serves unauthenticated; no known backdoor; no live key on disk.**

**Week 2 — Persistence & money safety** *(P0-5, P0-6, P1-4, P1-7, P1-11)*
WAL/busy_timeout/FK PRAGMAs (P0-5) first — it unblocks the backup work (P1-7) and the dedup migration (P1-4). Add the LLM rate-limit/cost cap (P0-6, independent, can run in parallel). Consolidate schema/migrations (P1-11). **Gate: no `database is locked` under concurrent writers; FKs enforced; daily cost ceiling; backups running.**

**Week 3 — Runtime robustness & event-loop health** *(P1-5, P1-6, P1-13, plus P2 background-loop guards)*
Move blocking sync off the loop (P1-5), bound retrieval (P1-6), wire token refresh (P1-13). Fold in the cheap P2 loop-guards (cluster_health, watchdog, WS disconnect) since they touch the same files. P1-5 and P1-6 are independent and parallelizable. **Gate: a slow upstream cannot wedge the backend; brain queries stay bounded.**

**Week 4 — Deploy, CI/CD & observability** *(P1-8, P1-9, P1-10, P1-12)*
Dockerfile + compose + IaC (P1-8) and CI/dev-env fixes (P1-9) first; CD (P1-10) depends on both. Observability (P1-12: metrics + Sentry + readyz) runs fully in parallel — different engineer, no shared files. **Gate: one-command reproducible build; green CI on the real suite; health-gated deploy; metrics + error tracking live.**

**Week 5 — Frontend production-fit & integrity hardening** *(P1-2, P1-3, P1-14, P1-15)*
WS-URL + client-auth (P1-14, P1-15) are small and depend on the Week 1 auth model + reverse proxy from Week 4. Signing-key hardening (P1-2) and receipt-chain tamper-evidence (P1-3) are the heavier crypto items — P1-3 is L and can start in Week 4 in parallel since it's backend-isolated. **Gate: live UI works behind a proxy with auth; receipts are tamper-evident and signed by a managed key.**

**Week 6+ — P2 burn-down**, then P3 polish. P2 governance-enforcement items (CORRECT semantics, approval binding, ALLOW transactionality), SSRF guard, and the test-coverage build-out (E2E WS test, governance regression tests) are the highest-value P2s once the P0/P1 foundation holds.

**Parallelization summary:** the observability track (P1-12), the LLM cost-cap (P0-6), and the receipt-chain work (P1-3) are largely file-isolated and can run continuously alongside the critical path. The serial spine is: **auth-defaults → DB PRAGMAs → schema/migrations → deploy artifact → CD**.

---

## 7. What's already solid

These areas were affirmatively verified as production-grade (findings exist *clearing* them, or document a correct positive):

- **Core auth/authz primitives** *(AUTHZ-007)*: the global HTTP middleware and `/ws/brain` auth are correctly implemented and fail-closed *when enabled* (constant-time `hmac.compare_digest`, WS closes 1011/1008 before `accept()`, query-string WS tokens off by default). Passports are Ed25519-signed and verified each use, with expiry/not-before/revoked/kill-switch enforced, public-endpoint TTL capped at 24h, and wildcard scopes rejected by default. The failures above are in *defaults and one hardcoded constant*, not the enforcement machinery. `tests/test_studio_auth.py` already covers the key cases.
- **Webhook signature verification** *(WEBHOOK-HMAC-CLEARED)*: GitHub/Slack/Linear HMAC-SHA256 with constant-time compare over the raw body (Slack adds a 5-minute replay window); Gmail via Google-signed Pub/Sub JWT with audience + issuer allowlist. Forged inbound events are correctly rejected.
- **OAuth CSRF state** *(OAUTH-STATE-CSRF-CLEARED)*: random `secrets.token_urlsafe(24)`, server-side, one-time, vendor-bound, constant-time compared.
- **SQL/FTS injection** *(SQL-INJECTION-CLEARED)*: parameterized SQLAlchemy everywhere across ~60 inspected call sites; the user question is matched in pure Python, never entering SQL — no injection in any verified path including Ask/search.
- **Unsafe deserialization / eval** *(DESERIALIZATION-EVAL-CLEARED)*: no `pickle`, no `yaml.load`, no `eval/exec` on user input; SkillFile conditions use a constrained predicate DSL, not Python eval; `yaml.safe_load` throughout.
- **Frontend XSS** *(XSS-FRONTEND-CLEARED)*: the only `innerHTML` sink interpolates a static typed-enum label, not user/ingested data; no markdown/HTML rendering of Ask answers; no `dangerouslySetInnerHTML`.
- **Ask-the-Brain input validation** *(ASK-BRAIN-INPUT-CLEARED)*: question length-bounded, `top_k`/`max_tokens` clamped, provider allow-listed, context capped; the only outbound call passes the question as message content, not a URL.
- **Vault discipline** *(SEC-KEY-RESOLUTION-LOGGING, OAUTH-ERROR-RESPONSE-LOGGING positives)*: application logs record key *presence/source*, never values; tokens are passed as Bearer headers and the vault store is explicitly "do not log return value."
- **Git history** *(SEC-GIT-HISTORY-CLEAN-CONFIRMED)*: across all 147 commits, `.env` was never tracked and no live secret was ever committed — only test fixtures. No history rewrite needed for credential leakage.
- **Type discipline** *(FE-FETCH-UNVALIDATED-CAST context)*: frontend `tsconfig` is `strict: true` with zero `any` casts in non-test source; backend has `mypy --strict` in CI.
- **A committed `uv.lock` and frontend `package-lock.json` exist** — the pinning machinery is present; the gap is only that CI doesn't install from them (P1-9).

The recurring good news: the project's hard parts (cryptographic signing, HMAC verification, injection-safe data access, CSRF) are done correctly. The work ahead is overwhelmingly about **changing permissive defaults to safe ones, wiring existing pieces together, and building the operational shell** (deploy, backups, observability) the system has never had.
