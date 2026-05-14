# AXIOM-BRAIN Full Line-by-Line Audit

Date: 2026-05-12
Auditor: Codex
Workspace: `/home/harsh/AXIOM-BRAIN`

## Scope

This audit covers the application source, frontend source, tests, migrations, configuration, policies, examples, fixtures, and project documentation. It excludes dependency directories, build output, binary/runtime state, caches, DB files, ignored worktrees, and generated agent scaffolding listed under Exclusions.

The repository contains a local `.env` with `AXIOM_VAULT_KEY` set. Its value was intentionally not copied into this report. `.gitignore` ignores `.env`.

## Method

- Enumerated auditable files and line counts.
- Reviewed high-risk code paths line-by-line: API auth, WebSocket auth, MCP passport enforcement, OAuth callbacks, webhook verification, secrets/vault handling, connector HTTP calls, dependency manifests, Docker/runtime config, and frontend token handling.
- Searched every scoped source/test/config/doc path for risky patterns: `secret`, `token`, `Authorization`, CORS, webhook signatures, `eval`, dynamic HTML, storage, subprocess use, disabled tests, stubs, broad exception handling, and missing dependency indicators.
- Did not run tests or builds; this is a static audit artifact.

## Findings

### Critical: MCP tools silently grant a full-scope demo passport when no passport token is supplied

Evidence:

- `src/axiom/mcp/server.py:230` resolves `passport_token`.
- `src/axiom/mcp/server.py:232` verifies only when a token is present.
- `src/axiom/mcp/server.py:234` falls back to `ensure_system_passport(...)` when no token is supplied.
- `src/axiom/govern/passports.py:17` defines `SYSTEM_PASSPORT_ID = "demo_passport"`.
- `src/axiom/govern/passports.py:18` defines `SYSTEM_PASSPORT_TOKEN = "demo_passport"`.
- `src/axiom/govern/passports.py:207` starts `ensure_system_passport`.
- `src/axiom/govern/passports.py:214-222` creates a one-year wildcard internal passport with the static bearer token.
- `tests/test_agent_passports.py:200` asserts actions without a provided passport use the default system passport.

Impact: If the MCP server is exposed beyond a trusted local process, missing credentials become an implicit full-scope identity. The static token is also knowable from source. This undermines passport-based authz for read and write tools.

Recommendation: Require an explicit passport token for all non-demo MCP calls. Only enable the system passport behind a hard demo flag that is disabled in production, never use a static bearer token, and scope any fallback identity to read-only demo data.

### High: OAuth callbacks accept `state` but never validate it against the state generated during install

Evidence:

- `src/axiom/studio/auth.py:34-37` exempts connector callbacks from API auth.
- `src/axiom/studio/server.py:1047-1050` generates and persists a GitHub install state.
- `src/axiom/studio/server.py:1053-1057` accepts GitHub callback `state` but exchanges `code` without comparing it.
- `src/axiom/studio/server.py:1226-1229` generates and persists Linear state.
- `src/axiom/studio/server.py:1232-1236` accepts Linear callback `state` without comparing it.
- `src/axiom/studio/server.py:1418-1421` generates and persists Slack state.
- `src/axiom/studio/server.py:1424-1428` accepts Slack callback `state` without comparing it.
- `src/axiom/studio/server.py:1615-1618` generates and persists Notion state.
- `src/axiom/studio/server.py:1621-1625` accepts Notion callback `state` without comparing it.
- `src/axiom/studio/server.py:1784-1787` generates and persists Gmail state.
- `src/axiom/studio/server.py:1790-1794` accepts Gmail callback `state` without comparing it.
- `tests/test_github_connector.py:336`, `tests/test_linear_connector.py:257`, and `tests/test_connectors_e2e_smoke.py:93` use fixed callback state values but do not test rejection of mismatched state.

Impact: Login CSRF or connector account mix-up is possible. An attacker who can cause an authenticated admin/browser to complete a callback can bind the wrong external account or complete an unsolicited install flow.

Recommendation: Store install state server-side with provider, expiry, and one-time-use semantics. On callback, reject missing/mismatched/expired state before exchanging `code`, then delete the state after success or failure.

### High: Invalid webhook signatures are parsed, persisted, and broadcast instead of rejected

Evidence:

- `src/axiom/studio/server.py:970-976` blocks graph ingestion when `signature_ok` is false.
- `src/axiom/studio/server.py:1143-1184` GitHub webhook route parses, stores, commits, and broadcasts events regardless of `signature_ok`.
- `src/axiom/studio/server.py:1335-1376` Linear webhook route follows the same pattern.
- `src/axiom/studio/server.py:1531-1575` Slack webhook route follows the same pattern.
- `src/axiom/studio/server.py:1870-1910` Gmail webhook route follows the same pattern.

Impact: Unsigned attacker payloads do not enter the graph, but they can still fill connector event storage, trigger UI/broadcaster activity, and create operational noise. This is a DB/event-stream injection and DoS risk.

Recommendation: Verify signatures before parsing into business events where possible. Return `401` or `403` on failed signature, do not persist unsigned events by default, and rate-limit public webhook endpoints.

### High: Runtime dependency `requests` is used by production source but is absent from `pyproject.toml`

Evidence:

- `pyproject.toml:6-18` lists runtime dependencies and does not include `requests`.
- `src/axiom/connectors/github/oauth.py:5`, `src/axiom/connectors/github/ingest.py:5`, and `src/axiom/connectors/github/writer.py:6` import `requests`.
- `src/axiom/connectors/gmail/oauth.py:8`, `src/axiom/connectors/gmail/ingest.py:6`, `src/axiom/connectors/gmail/webhook.py:9`, and `src/axiom/connectors/gmail/writer.py:7` import `requests`.
- `src/axiom/connectors/linear/oauth.py:6`, `src/axiom/connectors/linear/ingest.py:5`, and `src/axiom/connectors/linear/writer.py:5` import `requests`.
- `src/axiom/connectors/notion/oauth.py:6`, `src/axiom/connectors/notion/ingest.py:5`, `src/axiom/connectors/notion/poller.py:6`, and `src/axiom/connectors/notion/writer.py:5` import `requests`.
- `src/axiom/connectors/slack/oauth.py:7`, `src/axiom/connectors/slack/ingest.py:6`, and `src/axiom/connectors/slack/writer.py:5` import `requests`.

Impact: A clean install or Docker build can produce a runtime where connector flows crash with `ModuleNotFoundError: requests`, unless a transitive dependency happens to provide it. Runtime dependencies should not rely on transitive packages.

Recommendation: Add `requests` as a direct runtime dependency. Add `types-requests` to dev dependencies if strict mypy remains enabled.

### Medium: Dev/test dependency declarations are incomplete

Evidence:

- `tests/test_connectors_e2e_smoke.py:13`, `tests/test_github_connector.py:10`, `tests/test_gmail_connector.py:10`, `tests/test_linear_connector.py:10`, `tests/test_notion_connector.py:7`, and `tests/test_slack_connector.py:10` import `responses`.
- `pyproject.toml:21-27` lists dev dependencies but does not include `responses`.
- `frontend/package.json:10` defines `"lint": "eslint ."`.
- `frontend/package.json:21-35` lists frontend dev dependencies but does not include `eslint` or TypeScript ESLint packages.
- No `eslint` package reference was found in `frontend/package-lock.json`.

Impact: Fresh contributor/CI environments are likely to fail connector tests and frontend lint commands before reaching application code.

Recommendation: Add `responses` to Python dev dependencies. Either add the appropriate ESLint packages/config or remove/replace the lint script.

### Medium: API auth is fail-open by default outside the Docker production defaults

Evidence:

- `.env.example:20` leaves `AXIOM_API_TOKEN` blank.
- `.env.example:25` sets `AXIOM_AUTH_REQUIRED=0`.
- `src/axiom/studio/auth.py:23-24` makes auth required only when a token exists or `AXIOM_AUTH_REQUIRED` is truthy.
- `src/axiom/studio/server.py:684-687` skips auth middleware when `auth_required()` is false.
- `tests/test_studio_auth.py:22-28` asserts API auth is disabled by default.
- `docs/PRODUCTION.md:9-15` correctly tells operators to set production auth variables.

Impact: Running the app directly without the production runbook exposes internal write routes for settings, connector config, passports, skills, approvals, and secrets metadata. This is acceptable for local-only dev but dangerous if a direct `uvicorn` process is exposed.

Recommendation: Fail closed when `AXIOM_ENV=production`, when bound to non-loopback hosts, or when a frontend build is served. Keep local dev opt-out explicit.

### Medium: Browser API token is stored in `localStorage` and sent in the WebSocket query string

Evidence:

- `frontend/src/lib/apiAuth.ts:1` defines the storage key `AXIOM_API_TOKEN`.
- `frontend/src/lib/apiAuth.ts:6` reads the token from `window.localStorage`.
- `frontend/src/lib/apiAuth.ts:35-36` injects the token as an HTTP bearer token.
- `frontend/src/lib/apiAuth.ts:49-53` appends the token as `/ws/brain?token=...`.
- `.env.example:17-18` documents WebSocket query-token usage.
- `src/axiom/studio/auth.py:47-51` accepts `token` from the query string.

Impact: Any frontend XSS can read the token from localStorage. Query-string tokens can leak through browser history, reverse-proxy access logs, observability tools, or copied URLs.

Recommendation: Prefer HttpOnly secure same-site cookies for browser auth. For WebSockets, authenticate via cookie, subprotocol, or an initial authenticated message rather than a query parameter.

### Medium: Gmail webhook verification is stubbed off in the production route

Evidence:

- `src/axiom/connectors/gmail/webhook.py:16-18` uses `_default_verify_google_jwt` when no verifier is injected.
- `src/axiom/connectors/gmail/webhook.py:60-61` returns `False` for every default token.
- `src/axiom/studio/server.py:1874` instantiates `GmailWebhookHandler()` with no verifier.
- `src/axiom/studio/server.py:1886-1890` passes `signature_ok` into graph ingestion, which returns `0` when false.
- `tests/test_gmail_connector.py:125-131` only tests verification with an injected lambda verifier.

Impact: Gmail push webhooks will not ingest in the actual FastAPI route. They will still be persisted/broadcast as unsigned events per the webhook finding above.

Recommendation: Implement Google Pub/Sub/JWT verification for the route or mark Gmail webhook mode as disabled until verification exists.

### Medium: LLM key storage silently auto-generates a local vault key when `AXIOM_VAULT_KEY` is missing

Evidence:

- `src/axiom/govern/llm_keys.py:27` defines `KEY_FILE = Path(".axiom_vault_key")`.
- `src/axiom/govern/llm_keys.py:70-88` reads or creates that local key file when `AXIOM_VAULT_KEY` is unset.
- `src/axiom/vault/crypto.py:25-35` treats missing `AXIOM_VAULT_KEY` as a locked vault instead.
- `.gitignore:20` ignores `.axiom_vault_key`, but runtime storage still depends on a local cleartext file.

Impact: Secret handling is inconsistent. In production, a process can create an unknown local key, encrypt LLM keys with it, and lose access on container replacement or filesystem rotation. It also places a cleartext master key in the working directory.

Recommendation: Use the same vault crypto path for all secrets. Runtime should fail locked when the master key is missing; key generation should only happen through explicit `vault init` workflows.

### Medium: Passport issuance allows unbounded TTL and wildcard scopes from internal HTTP routes

Evidence:

- `src/axiom/studio/server.py:265-272` defines `PassportIn` with default wildcard scopes and `ttl_hours` only constrained to `gt=0`.
- `src/axiom/studio/server.py:275-281` defines agent registration with `ttl_hours` only constrained to `gt=0`.
- `src/axiom/studio/server.py:2109-2117` issues wildcard cluster/intent/skill passports during agent registration.
- `src/axiom/studio/server.py:2201-2218` issues user-requested passports directly from request body scope and TTL.
- `src/axiom/govern/passports.py:145-158` sets expiry using the caller-provided `ttl_hours`.

Impact: Anyone with internal API access can mint very long-lived broad-scope passports. Combined with fail-open local auth or leaked browser tokens, this expands blast radius.

Recommendation: Add a maximum TTL, default least-privilege scopes, role checks for wildcard scopes, and audit reasons for broad/long-lived tokens.

### Low: Several core modules exceed the repository’s own 500-line rule

Evidence:

- `CLAUDE.md:8` says to keep files under 500 lines.
- `src/axiom/studio/server.py` is 3,222 lines.
- `src/axiom/mcp/server.py` is 1,484 lines.
- `frontend/src/pages/GovernancePage.tsx` is 1,133 lines.
- `frontend/src/components/Brain.tsx` is 932 lines.
- `frontend/src/pages/InsightsPage.tsx` is 741 lines.
- `frontend/src/pages/SkillsPage.tsx` is 628 lines.

Impact: The main integration points are hard to audit, test, and safely change. This increases regression risk and makes security review harder.

Recommendation: Split by bounded responsibility: auth/middleware, connector routers, passport routes, skill routes, governance routes, WebSocket broadcasting, and frontend feature panels.

### Low: Broad exception swallowing hides operational failures

Evidence:

- `src/axiom/studio/server.py:475`, `src/axiom/studio/server.py:515`, `src/axiom/studio/server.py:523`, `src/axiom/studio/server.py:549`, `src/axiom/studio/server.py:555`, `src/axiom/studio/server.py:573`, `src/axiom/studio/server.py:586`, and `src/axiom/studio/server.py:726` catch broad exceptions around settings/startup/background work.
- `src/axiom/organize/agent.py` has many broad `except Exception` handlers around organizer loop behavior.
- `src/axiom/govern/watchdog.py` has multiple broad handlers around watchdog evaluation.

Impact: Background failures can silently degrade production behavior. Some best-effort loops should survive exceptions, but they still need structured logging, metrics, and visible health status.

Recommendation: Replace silent `pass` paths with structured logs and health counters. Only suppress expected exception classes where possible.

## Positive controls observed

- `.gitignore` excludes `.env`, SQLite DB files, runtime settings, local vault key, caches, output, Playwright artifacts, worktrees, and generated `.claude/` artifacts.
- Docker runtime sets `AXIOM_ENV=production` and `AXIOM_AUTH_REQUIRED=1`.
- Connector OAuth access/refresh tokens are vault-referenced instead of stored directly in connector state rows.
- Webhook graph ingestion is blocked when signatures are invalid.
- Most external HTTP calls include explicit timeouts.
- Search and list endpoints generally bound user-controlled `limit` values.
- Production docs clearly state this is single-tenant and requires a strong API token.

## Exclusions

The following were excluded from line-by-line code review because they are dependencies, generated artifacts, binary/runtime state, local caches, ignored worktrees, or secret-bearing local files:

- `.git/`
- `.claude/` generated agent/skill scaffolding and commands, ignored by `.gitignore`
- `.claude-flow/`
- `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `*.pyc`
- `.playwright-cli/`, `.playwright-mcp/`
- `.swarm/`
- `.worktrees/`
- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/tsconfig.tsbuildinfo`
- `dist/`, `build/`, `target/`, `coverage/`
- `*.db`, `*.db-shm`, `*.db-wal`, `*.sqlite`, `*.sqlite-shm`, `*.sqlite-wal`
- `.env` value content; only variable names and presence were audited
- `output/` logs and dogfood screenshots/snapshots

## Local secret-bearing file check

- `.env:1` contains `AXIOM_VAULT_KEY=<set>`.
- `.gitignore:12` ignores `.env`.
- `.gitignore:20` ignores `.axiom_vault_key`.

## Line coverage ledger

The following ledger records every scoped file included in the static audit surface and its line count.

```text
     14 .dockerignore
     36 .env.example
     36 .gitignore
     21 .mcp.json
    175 CLAUDE.md
   1168 DESIGN.md
     24 Dockerfile
     21 LICENSE
    419 NOTES.md
     98 README.md
    149 alembic.ini
     84 alembic/env.py
     28 alembic/script.py.mako
    153 alembic/versions/309b33ebec31_initial_schema.py
     55 alembic/versions/a1b2c3d4e5f6_add_cluster_id_and_importance.py
    124 alembic/versions/a2b3c4d5e6f7_phase_16_18_connectors.py
     36 alembic/versions/a7d8e9f0a1b2_phase_7d_llm_provider_keys.py
     55 alembic/versions/b2c3d4e5f6a7_add_secrets_table.py
    119 alembic/versions/b8e9f0a1b2c3_phase_8_skills_emitter.py
     84 alembic/versions/c3d4e5f6a7b8_phase_7_receipts_schema_b.py
     68 alembic/versions/c9d0e1f2a3b4_phase_8_5_agent_passports.py
     43 alembic/versions/d0e1f2a3b4c5_phase_8_6_entity_embeddings.py
     45 alembic/versions/d4e5f6a7b8c9_phase_7a_metrics_snapshots.py
     64 alembic/versions/e1f2a3b4c5d6_phase_5_8_watchdog_alerts.py
     46 alembic/versions/e5f6a7b8c9d0_phase_7b_agent_registry.py
     84 alembic/versions/f2a3b4c5d6e7_phase_16_approvals.py
     62 alembic/versions/f6a7b8c9d0e1_phase_7c_cluster_check_runs.py
    815 docs/AUDIT_CLAUDE_CODE_2026-05-10.md
    399 docs/AUDIT_CODEX_2026-05-10.md
    693 docs/AUDIT_CURSOR_2026-05-10.md
    191 docs/AXIOM_AUDIT_BRIEF.md
    176 docs/AXIOM_AUDIT_REPORT.md
    441 docs/AXIOM_COMPANY_BRAIN_AUDIT.md
    726 docs/AXIOM_PHASE_5_12_SPEC.md
    549 docs/CODEX_REBUILD_BRIEF.md
     98 docs/CONNECTORS.md
    277 docs/FULL_LINE_BY_LINE_AUDIT_2026-05-12.md
     99 docs/POLICIES.md
     43 docs/PRODUCTION.md
    565 docs/ROADMAP.md
     53 docs/SKILLS.md
     26 examples/skills/classify_ticket_priority.md
     25 examples/skills/extract_decision.md
     23 examples/skills/summarize_thread.md
   2335 fixtures/synthetic_company.json
     13 frontend/index.html
   4329 frontend/package-lock.json
     36 frontend/package.json
      7 frontend/postcss.config.cjs
      6 frontend/public/favicon.svg
    268 frontend/src/App.tsx
    234 frontend/src/__tests__/CommandPalette.test.tsx
    164 frontend/src/__tests__/HUD.test.tsx
     25 frontend/src/__tests__/aegis-gate.test.ts
     30 frontend/src/__tests__/aegis-particles.test.ts
    130 frontend/src/__tests__/agents-subroutes.test.tsx
     97 frontend/src/__tests__/ai-insight-card.test.tsx
     54 frontend/src/__tests__/app-title.test.tsx
    136 frontend/src/__tests__/approvals-ui.test.tsx
     39 frontend/src/__tests__/arrival-effect.test.ts
     28 frontend/src/__tests__/auto-orbit.test.ts
     22 frontend/src/__tests__/brain-envelope-lobes.test.ts
     22 frontend/src/__tests__/brain-envelope.test.ts
     90 frontend/src/__tests__/brain-health-history.test.tsx
    276 frontend/src/__tests__/brain.store.test.ts
     17 frontend/src/__tests__/brand-mark.test.tsx
     79 frontend/src/__tests__/camera-flyto.test.ts
     19 frontend/src/__tests__/camera-reset.test.ts
    118 frontend/src/__tests__/chrome-rebuild.test.tsx
     95 frontend/src/__tests__/cluster-aura.test.ts
     59 frontend/src/__tests__/cluster-bracket-label.test.tsx
     32 frontend/src/__tests__/cluster-force-layout.test.ts
     21 frontend/src/__tests__/cluster-hub-icon.test.ts
     34 frontend/src/__tests__/cluster-label-collision.test.ts
    205 frontend/src/__tests__/cluster-layout.test.ts
     52 frontend/src/__tests__/cluster-mesh.test.ts
    322 frontend/src/__tests__/connectors-page.test.tsx
     63 frontend/src/__tests__/curved-conduits.test.ts
     23 frontend/src/__tests__/edge-animation.test.ts
     13 frontend/src/__tests__/edge-shimmer.test.ts
     36 frontend/src/__tests__/edge-style.test.ts
     16 frontend/src/__tests__/edge-tint.test.ts
     55 frontend/src/__tests__/export.test.ts
     43 frontend/src/__tests__/fps-guard.test.ts
     13 frontend/src/__tests__/fps.test.ts
     98 frontend/src/__tests__/governance-controls.test.tsx
     17 frontend/src/__tests__/hex-geometry.test.ts
    147 frontend/src/__tests__/hex-layout.test.ts
     55 frontend/src/__tests__/idle-orbit.test.ts
     23 frontend/src/__tests__/idle-pulse.test.ts
     58 frontend/src/__tests__/insights-controls.test.tsx
    204 frontend/src/__tests__/inspector.test.tsx
    250 frontend/src/__tests__/labels.test.ts
     70 frontend/src/__tests__/lod.test.ts
     25 frontend/src/__tests__/palette.test.ts
    166 frontend/src/__tests__/particle-behaviors.test.ts
     88 frontend/src/__tests__/particle-flow.test.ts
    144 frontend/src/__tests__/passports-page.test.tsx
    547 frontend/src/__tests__/phase-13b-ui.test.tsx
     77 frontend/src/__tests__/radial-traffic.test.ts
     32 frontend/src/__tests__/reactive-spawn.test.ts
     29 frontend/src/__tests__/reconnect-hud.test.tsx
     29 frontend/src/__tests__/relative-api-urls.test.ts
     18 frontend/src/__tests__/renderer-kind.test.ts
     40 frontend/src/__tests__/satellite-pack.test.ts
    180 frontend/src/__tests__/settings-page.test.tsx
     16 frontend/src/__tests__/sphere-geometry.test.ts
     35 frontend/src/__tests__/spoke-shimmer.test.ts
     60 frontend/src/__tests__/synaptic-flow.test.ts
    158 frontend/src/__tests__/vault-client.test.ts
    142 frontend/src/__tests__/watchdog-policy-ui.test.tsx
     15 frontend/src/__tests__/webgpu-detect.test.ts
    111 frontend/src/__tests__/websocket.test.ts
     99 frontend/src/components/AIInsightCard.tsx
     38 frontend/src/components/ArrivalEffect.tsx
      8 frontend/src/components/AxiomGlyph.tsx
    932 frontend/src/components/Brain.tsx
      4 frontend/src/components/BrainCanvas.tsx
    218 frontend/src/components/BrainHealthCard.tsx
     18 frontend/src/components/BrandMark.tsx
     78 frontend/src/components/ClusterAura.tsx
     71 frontend/src/components/ClusterBracketLabel.tsx
     54 frontend/src/components/ClusterHubIcon.tsx
    362 frontend/src/components/CommandPalette.tsx
     21 frontend/src/components/EdgeLegend.tsx
    484 frontend/src/components/EntityInspector.tsx
    154 frontend/src/components/HUD.tsx
      5 frontend/src/components/HexGridBackground.tsx
    107 frontend/src/components/NavRail.tsx
     49 frontend/src/components/PendingApprovalsBadge.tsx
      4 frontend/src/components/PhaseStubApp.tsx
     93 frontend/src/components/QueryBar.tsx
     39 frontend/src/components/StatusFooter.tsx
     17 frontend/src/components/TopHeader.tsx
     10 frontend/src/components/__tests__/phase_stub.test.ts
    151 frontend/src/components/settings/AddKeyDialog.tsx
    125 frontend/src/components/settings/ProviderCard.tsx
     15 frontend/src/components/settings/SectionHeader.tsx
     35 frontend/src/components/settings/StatusPill.tsx
    155 frontend/src/hooks/__tests__/useBrainFocus.test.ts
     12 frontend/src/hooks/useBrainFocus.ts
     69 frontend/src/lib/aegis-gate.ts
     90 frontend/src/lib/aegis-particles.ts
     91 frontend/src/lib/agentsClient.ts
     56 frontend/src/lib/apiAuth.ts
     64 frontend/src/lib/approvalsClient.ts
     29 frontend/src/lib/auto-orbit.ts
     32 frontend/src/lib/brain-envelope.ts
     75 frontend/src/lib/camera-flyto.ts
     10 frontend/src/lib/camera-reset.ts
    261 frontend/src/lib/cluster-force-layout.ts
     40 frontend/src/lib/cluster-label-collision.ts
    192 frontend/src/lib/cluster-layout.ts
     82 frontend/src/lib/cluster-mesh.ts
     51 frontend/src/lib/cluster-reframe.ts
     90 frontend/src/lib/curved-conduits.ts
     16 frontend/src/lib/edge-animation.ts
     42 frontend/src/lib/edge-style.ts
     17 frontend/src/lib/edge-tint.ts
     35 frontend/src/lib/export.ts
     93 frontend/src/lib/fps-guard.ts
     19 frontend/src/lib/fps.ts
     14 frontend/src/lib/hex-geometry.ts
     99 frontend/src/lib/hex-grid-bg.ts
    168 frontend/src/lib/hex-layout.ts
     40 frontend/src/lib/idle-orbit.ts
     18 frontend/src/lib/idle-pulse.ts
     19 frontend/src/lib/inspector.ts
     66 frontend/src/lib/labels.ts
     57 frontend/src/lib/llmKeysClient.ts
     63 frontend/src/lib/lod.ts
     31 frontend/src/lib/palette.ts
    297 frontend/src/lib/particle-behaviors.ts
    201 frontend/src/lib/particle-flow.ts
    187 frontend/src/lib/particles/agent-effects.ts
     97 frontend/src/lib/particles/edge-shimmer.ts
     42 frontend/src/lib/particles/idle-pulse-runner.ts
     58 frontend/src/lib/particles/nebula-bg.ts
     49 frontend/src/lib/particles/orbital-halo.ts
     97 frontend/src/lib/particles/reactive-spawn.ts
    168 frontend/src/lib/particles/synaptic-flow.ts
     80 frontend/src/lib/passportsClient.ts
    126 frontend/src/lib/radial-traffic.ts
    105 frontend/src/lib/satellite-pack.ts
    147 frontend/src/lib/skillsClient.ts
      8 frontend/src/lib/sphere-geometry.ts
     24 frontend/src/lib/spoke-shimmer.ts
     50 frontend/src/lib/studioClient.ts
    163 frontend/src/lib/vaultClient.ts
     48 frontend/src/lib/vaultTypes.ts
     40 frontend/src/lib/watchdogClient.ts
     14 frontend/src/lib/webgpu-detect.ts
    132 frontend/src/lib/websocket.ts
     14 frontend/src/main.tsx
    294 frontend/src/pages/AgentsPage.tsx
    495 frontend/src/pages/ConnectorsPage.tsx
    543 frontend/src/pages/ExplorePage.tsx
   1133 frontend/src/pages/GovernancePage.tsx
    741 frontend/src/pages/InsightsPage.tsx
    204 frontend/src/pages/PassportsPage.tsx
    369 frontend/src/pages/SettingsPage.tsx
    628 frontend/src/pages/SkillsPage.tsx
     74 frontend/src/pages/agents/ActivityPage.tsx
    147 frontend/src/pages/agents/ApprovalsPage.tsx
     55 frontend/src/pages/agents/RuntimePage.tsx
     47 frontend/src/pages/agents/SchedulesPage.tsx
     47 frontend/src/pages/agents/TriggersPage.tsx
     41 frontend/src/pages/agents/shared.tsx
    405 frontend/src/state/brain.store.ts
    214 frontend/src/state/settings.store.ts
      8 frontend/src/test/setup.ts
     10 frontend/tailwind.config.ts
     22 frontend/tsconfig.json
     26 frontend/vite.config.ts
      6 policies/intelligent.yaml
     27 policies/starter-pack/00-passport-state.yaml
     29 policies/starter-pack/01-scope-enforcement.yaml
     44 policies/starter-pack/02-data-safety.yaml
     20 policies/starter-pack/03-temporal.yaml
     20 policies/starter-pack/04-confidence-gates.yaml
     22 policies/starter-pack/05-watchdog-integration.yaml
     53 pyproject.toml
    358 scripts/generate_fixture.py
     22 src/axiom/__init__.py
      1 src/axiom/api/__init__.py
    124 src/axiom/api/search.py
    156 src/axiom/cli.py
     24 src/axiom/connectors/__init__.py
    117 src/axiom/connectors/base.py
     27 src/axiom/connectors/github/__init__.py
    101 src/axiom/connectors/github/ingest.py
     47 src/axiom/connectors/github/oauth.py
     45 src/axiom/connectors/github/webhook.py
     82 src/axiom/connectors/github/writer.py
      8 src/axiom/connectors/gmail/__init__.py
    105 src/axiom/connectors/gmail/ingest.py
     99 src/axiom/connectors/gmail/oauth.py
     80 src/axiom/connectors/gmail/webhook.py
     89 src/axiom/connectors/gmail/writer.py
     93 src/axiom/connectors/ingest.py
      8 src/axiom/connectors/linear/__init__.py
    128 src/axiom/connectors/linear/ingest.py
     52 src/axiom/connectors/linear/oauth.py
     38 src/axiom/connectors/linear/webhook.py
     94 src/axiom/connectors/linear/writer.py
      8 src/axiom/connectors/notion/__init__.py
    100 src/axiom/connectors/notion/ingest.py
     52 src/axiom/connectors/notion/oauth.py
     66 src/axiom/connectors/notion/poller.py
     79 src/axiom/connectors/notion/writer.py
     80 src/axiom/connectors/registry.py
      8 src/axiom/connectors/slack/__init__.py
    145 src/axiom/connectors/slack/ingest.py
     71 src/axiom/connectors/slack/oauth.py
     92 src/axiom/connectors/slack/webhook.py
     90 src/axiom/connectors/slack/writer.py
     87 src/axiom/connectors/writer.py
      1 src/axiom/govern/__init__.py
    170 src/axiom/govern/agent_actions.py
    118 src/axiom/govern/agent_registry.py
    217 src/axiom/govern/approvals.py
    163 src/axiom/govern/cluster_checks.py
     23 src/axiom/govern/demo_flag.py
     27 src/axiom/govern/ledger.py
    246 src/axiom/govern/llm_keys.py
    354 src/axiom/govern/passports.py
    112 src/axiom/govern/policy_evaluator.py
    219 src/axiom/govern/receipts.py
    167 src/axiom/govern/snapshots.py
     68 src/axiom/govern/verify.py
     61 src/axiom/govern/warden.py
    388 src/axiom/govern/watchdog.py
    376 src/axiom/govern/watchdog_rules.py
      4 src/axiom/ingest/__init__.py
     57 src/axiom/ingest/broadcaster.py
     34 src/axiom/ingest/interfaces.py
    144 src/axiom/ingest/pipeline.py
     11 src/axiom/mcp/__init__.py
     29 src/axiom/mcp/interfaces.py
   1484 src/axiom/mcp/server.py
     16 src/axiom/organize/__init__.py
    342 src/axiom/organize/agent.py
    180 src/axiom/organize/centrality.py
    218 src/axiom/organize/classifier.py
    103 src/axiom/organize/cluster_health.py
    124 src/axiom/organize/clusters.py
    115 src/axiom/organize/edge_proposer.py
     51 src/axiom/policy/__init__.py
    525 src/axiom/policy/dsl.py
    121 src/axiom/policy/evaluator.py
     23 src/axiom/policy/interfaces.py
    246 src/axiom/policy/predicates.py
     45 src/axiom/policy/watchdog_integration.py
     25 src/axiom/providers/__init__.py
    163 src/axiom/providers/connectors.py
     11 src/axiom/providers/errors.py
    112 src/axiom/providers/llm.py
     47 src/axiom/providers/models.py
     15 src/axiom/providers/oauth.py
    170 src/axiom/providers/registry.py
     85 src/axiom/providers/router.py
     25 src/axiom/providers/verify.py
      0 src/axiom/retrieval/__init__.py
    235 src/axiom/retrieval/embeddings.py
    302 src/axiom/retrieval/search.py
     28 src/axiom/schema/__init__.py
     99 src/axiom/schema/dto.py
    405 src/axiom/schema/models.py
      5 src/axiom/sign/__init__.py
    119 src/axiom/sign/ed25519_signer.py
     32 src/axiom/sign/interfaces.py
     14 src/axiom/skills/__init__.py
    210 src/axiom/skills/emitter.py
     27 src/axiom/skills/interfaces.py
    279 src/axiom/skills/registry.py
    414 src/axiom/skills/runner.py
    142 src/axiom/skills/skill_md.py
      4 src/axiom/sources/__init__.py
     66 src/axiom/sources/base.py
    389 src/axiom/sources/event_generators.py
     69 src/axiom/sources/interfaces.py
    164 src/axiom/sources/live_synthetic.py
     81 src/axiom/sources/synthetic.py
    114 src/axiom/storage/__init__.py
    157 src/axiom/storage/crud.py
     49 src/axiom/storage/db.py
      4 src/axiom/studio/__init__.py
     79 src/axiom/studio/auth.py
     45 src/axiom/studio/interfaces.py
     94 src/axiom/studio/llm_keys_api.py
   3222 src/axiom/studio/server.py
     71 src/axiom/studio/sources.py
    190 src/axiom/studio/vault_api.py
     69 src/axiom/vault/__init__.py
     76 src/axiom/vault/crypto.py
     47 src/axiom/vault/errors.py
     63 src/axiom/vault/models.py
    208 src/axiom/vault/store.py
      1 tests/__init__.py
     33 tests/conftest.py
     50 tests/test_agent_actions.py
    127 tests/test_agent_navigation_events.py
    312 tests/test_agent_passports.py
    278 tests/test_agent_registry.py
    265 tests/test_approvals.py
    111 tests/test_broadcaster_phase_3.py
     97 tests/test_cli_serve_live.py
    302 tests/test_cluster_check_runs.py
    101 tests/test_cluster_health.py
    165 tests/test_confidence_changed_events.py
     70 tests/test_connectors_config_api.py
    310 tests/test_connectors_e2e_smoke.py
    348 tests/test_connectors_framework.py
     87 tests/test_correct_decision_branch.py
     44 tests/test_design_doc.py
     94 tests/test_edge_proposer.py
     24 tests/test_fixture_generator_phase_3.py
    176 tests/test_fixture_shape_phase_3.py
    349 tests/test_github_connector.py
    286 tests/test_gmail_connector.py
    130 tests/test_ingest_pipeline_phase_3.py
     41 tests/test_ledger_warden.py
    270 tests/test_linear_connector.py
    140 tests/test_live_synthetic_source.py
    101 tests/test_llm_provider_keys.py
     35 tests/test_mcp_cli.py
    201 tests/test_mcp_read_tools.py
    574 tests/test_mcp_write_tools.py
    275 tests/test_metrics_snapshots.py
     20 tests/test_migrations.py
     64 tests/test_neighbors.py
    223 tests/test_notion_connector.py
    162 tests/test_organize_centrality.py
    191 tests/test_organize_classifier.py
    230 tests/test_organizer_agent.py
     43 tests/test_phase_3_guards.py
    273 tests/test_policy_dsl.py
    271 tests/test_policy_starter_pack.py
    305 tests/test_policy_wiring.py
    213 tests/test_provider_router.py
    209 tests/test_providers.py
    247 tests/test_receipts_phase_7.py
    266 tests/test_retrieval_phase_8_6.py
    107 tests/test_search_api.py
    281 tests/test_server_phase_3.py
    285 tests/test_sign_ed25519.py
    685 tests/test_skills_emitter.py
    296 tests/test_slack_connector.py
     30 tests/test_sources_base_phase_3.py
      7 tests/test_sources_real.py
     64 tests/test_storage.py
     64 tests/test_storage_public_api.py
    187 tests/test_stubs.py
     99 tests/test_studio_auth.py
     62 tests/test_synthetic_source_phase_3.py
    300 tests/test_vault.py
    311 tests/test_vault_api.py
    335 tests/test_watchdog.py
    271 tests/test_watchdog_policy_integration.py
  63339 total
```

## Static search coverage

High-risk searches were run across the scoped audit surface for:

- Auth and token handling: `AXIOM_API_TOKEN`, `Authorization`, bearer headers, API keys, passport tokens, WebSocket query tokens.
- Secrets handling: vault key, Fernet, encrypted key fields, connector OAuth client secrets, access tokens, refresh tokens, webhook secrets.
- Webhook and OAuth safety: signature verification, HMAC comparison, replay timestamps, callback state, CSRF/state references.
- Injection/dynamic execution: `eval`, `exec`, `subprocess`, `shell=True`, dynamic HTML, `dangerouslySetInnerHTML`, local/session storage.
- Test and quality gaps: `TODO`, `FIXME`, `NotImplementedError`, broad `except Exception`, skipped tests, focused tests, console/debugger usage.
- Dependency health: source imports compared against Python and frontend manifests.

## Residual risk

This is a static audit. I did not execute test suites, dependency installation, Docker builds, browser flows, migration upgrades, or live connector OAuth/webhook flows. The findings above are evidence-backed from source lines, but runtime-only failures may remain.

## Remediation status - 2026-05-12

The production-hardening pass addressed the critical and high-impact audit items found in this file:

- MCP write tools now fail closed without an explicit passport token unless the non-production demo fallback flag is enabled.
- WebSocket API authentication now uses subprotocol token transport; query-string token transport is disabled by default.
- Connector OAuth callbacks now validate and consume stored, expiring install state before token exchange.
- GitHub, Linear, Slack, and Gmail webhook routes now reject invalid signatures before parsing, storing, ingesting, or broadcasting events.
- Public passport issuance now blocks wildcard scopes by default and caps public TTLs at 24 hours.
- Agent registry passport auto-issuance now uses bounded external-MCP/read scopes instead of full wildcard scopes.
- The LLM key vault now fails closed when `AXIOM_VAULT_KEY` is missing instead of creating a local fallback key.
- Runtime dependency metadata now includes `requests`; test dependency metadata now includes `responses`.
- Frontend WebSocket clients now send API tokens via subprotocols instead of URL query parameters.
- Frontend passport and skill creation defaults no longer pre-fill wildcard scopes.
- Production documentation and `.env.example` now document the new fail-closed defaults and explicit demo escape hatches.

Validation evidence from this remediation pass:

- `pytest -q` -> `559 passed`
- `npm --prefix frontend test` -> `64 passed`, `402 passed`
- `npm --prefix frontend run lint` -> passed
- `npm --prefix frontend run build` -> passed

### Additional remediation note - Gmail Pub/Sub verification

The Gmail webhook verifier is no longer a permanent stub. It now validates Google Pub/Sub OIDC JWTs when `AXIOM_GMAIL_PUBSUB_AUDIENCE` is configured, optionally pins `AXIOM_GMAIL_PUBSUB_SERVICE_ACCOUNT`, and fails closed when verification cannot be performed.

Updated validation evidence:

- `pytest -q` -> `560 passed`
- `python -m ruff check src/axiom/connectors/gmail/webhook.py tests/test_gmail_connector.py` -> passed
- Full `python -m ruff check src tests` currently fails on the existing repository lint baseline.
- Full `python -m mypy` currently fails on the existing repository type-check baseline.
