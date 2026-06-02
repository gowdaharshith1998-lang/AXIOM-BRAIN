# AXIOM Production Runbook

AXIOM can run as a single-tenant production service when these controls are set.
It is not yet a multi-tenant SaaS with per-user RBAC.

## Required Environment

Set these before exposing the service:

```bash
AXIOM_ENV=production
AXIOM_AUTH_REQUIRED=1
AXIOM_API_TOKEN=<long random deployment token>
AXIOM_ALLOW_WS_QUERY_TOKEN=0
AXIOM_MCP_ALLOW_SYSTEM_PASSPORT=0
AXIOM_ALLOW_WILDCARD_PASSPORTS=0
AXIOM_OAUTH_STATE_TTL_SECONDS=600
AXIOM_GMAIL_PUBSUB_AUDIENCE=<gmail pubsub push oidc audience if Gmail enabled>
AXIOM_GMAIL_PUBSUB_SERVICE_ACCOUNT=<optional pubsub service account email>
AXIOM_VAULT_KEY=<python -m axiom.cli vault init output>
DATABASE_URL=<sqlalchemy url>
```

`AXIOM_ENV=production` disables demo simulator streams. `AXIOM_AUTH_REQUIRED=1`
fails closed if `AXIOM_API_TOKEN` is missing. `AXIOM_VAULT_KEY` encrypts connector
OAuth client secrets, webhook secrets, and provider access tokens.
Browser WebSockets authenticate with the `axiom.auth` subprotocol; query-string
WebSocket tokens are disabled unless `AXIOM_ALLOW_WS_QUERY_TOKEN=1` is explicitly
set for a short migration window. MCP tools require explicit passports in
production.

If Gmail is enabled, configure Pub/Sub push authentication with an OIDC token and
set `AXIOM_GMAIL_PUBSUB_AUDIENCE` to the exact audience value. Set
`AXIOM_GMAIL_PUBSUB_SERVICE_ACCOUNT` to pin delivery to one service account.
Without an audience, Gmail webhooks fail closed.

## Container

```bash
docker build -t axiom-brain .
docker run --env-file .env -p 8000:8000 axiom-brain
```

Or with Compose (named volume for the SQLite DB, healthcheck on `/readyz`):

```bash
AXIOM_API_TOKEN=<token> docker compose up --build
```

The image launches the module-level ASGI app directly:

```bash
uvicorn axiom.studio.server:app --host 0.0.0.0 --port 8000
```

The container serves the FastAPI API, `/ws/brain`, and the built React frontend
from one origin.

## Observability

- `GET /livez` — liveness probe, always `200` while the process is up.
- `GET /readyz` — readiness probe: runs `SELECT 1`, checks the vault is
  unlocked, and checks no background task has died with an exception. Returns
  `200` when healthy, `503` with a JSON `checks.failed[]` list otherwise.
- `GET /metrics` — Prometheus exposition (request count, an LLM/token counter
  hook, and a per-background-task liveness gauge). Degrades to a plain-text
  "metrics unavailable" `200` if `prometheus-client` is not installed.
- Every response carries an `X-Request-ID` header (generated if the request did
  not supply one).

## Connector Secrets

Connector setup endpoints accept plaintext once. The server stores OAuth client
secrets, webhook secrets, access tokens, and refresh tokens in the Fernet vault.
The connector tables retain only metadata and vault references.

## Ask the Brain

`POST /api/brain/ask` runs hybrid retrieval (lexical + semantic + graph) over
the ingested entity graph and sends a grounded prompt to a stored LLM provider
key. Register a key first:

```bash
curl -X POST https://<host>/api/internal/llm-keys \
  -H "Authorization: Bearer $AXIOM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "key": "sk-ant-..."}'
```

Supported providers: `anthropic` (default model
`claude-haiku-4-5-20251001`) and `openai` (`gpt-4o-mini`). The response
includes the answer text, structured `citations[]` referencing real entity IDs,
the provider/model used, token usage, and a `receipt` summary. Vault access
fails closed if `AXIOM_VAULT_KEY` is missing — the route returns `503`. No
provider key registered returns `409` so the frontend can prompt the operator
to add one. Upstream rate limits surface as `429`.

## Backups & Restore

AXIOM stores everything in one SQLite database (`axiom.db`): the full entity
graph **and** the hash-chained, Ed25519-signed receipt log (the audit trail).
Losing it loses the audit chain, so backups are a hard production requirement
(P1-7 / DB-004).

**Prerequisite — WAL mode.** Backups use `sqlite3 <db> ".backup <dest>"`, the
SQLite online-backup API, which produces a consistent snapshot even while the
app is actively writing. This is reliable because the DB runs in WAL mode
(`journal_mode=WAL`, `busy_timeout`, `foreign_keys=ON`), enabled at connect-time
by the P0-5 fix in a parallel workstream. Confirm with `scripts/verify_db.sh`
(reports `journal_mode`).

### Strategy & objectives

Two strategies; pick one:

| Strategy                         | RPO (data loss window) | RTO (time to restore) | How                                   |
| -------------------------------- | ---------------------- | --------------------- | ------------------------------------- |
| Daily snapshot (`scripts` + cron) | up to 24h              | minutes               | `scripts/backup_db.sh` on a schedule  |
| Litestream streaming replication | near-zero (seconds)    | minutes               | `litestream` sidecar (commented in compose) |

- **What is backed up:** the entire `axiom.db` file (graph + receipt chain), as
  a self-contained, integrity-checked SQLite snapshot. Connector secrets live in
  the Fernet vault and are encrypted with `AXIOM_VAULT_KEY` — back up that key
  **separately** in your secrets manager; a restored DB is unreadable without it.
- **RTO** is dominated by copying the chosen backup back into place and an
  integrity check — minutes for a 73MB DB.

### Scripts

All three are POSIX `sh`, fail loudly (non-zero exit), and live in `scripts/`:

- `scripts/backup_db.sh [DB_PATH] [BACKUP_DIR]` — online `.backup` to a
  timestamped file, runs `PRAGMA integrity_check` on the result (aborts if not
  `ok`), prunes to `BACKUP_RETENTION` (default 14), and copies offsite via
  `rclone` when `RCLONE_REMOTE` is set.
- `scripts/restore_db.sh BACKUP_FILE [DB_PATH]` — validates the backup, writes a
  pre-restore safety copy of the current DB, restores, runs a post-restore
  `integrity_check`, and prints the Alembic schema version.
- `scripts/verify_db.sh [DB_PATH]` — standalone `integrity_check` +
  `quick_check` and a `journal_mode`/`foreign_keys`/`busy_timeout` report; exits
  non-zero on failure (cron- and runbook-friendly).

`DB_PATH` defaults to `/data/axiom.db` (the compose volume mount); pass a
positional arg or set `AXIOM_DB_PATH` for other layouts (e.g. `./axiom.db` for a
bare `uvicorn` launch).

### Runbook

**Take a backup** (host cron pattern — one-shot container, DB volume read-only):

```bash
# Daily at 02:00; keep 14, optional offsite via RCLONE_REMOTE.
0 2 * * * cd /opt/axiom && RUN_ONCE=1 docker compose run --rm backup
```

Or run the script directly against a local DB:

```bash
BACKUP_RETENTION=14 RCLONE_REMOTE=s3:my-bucket/axiom \
  scripts/backup_db.sh ./axiom.db ./backups
```

Or run the long-lived loop sidecar (backs up every `BACKUP_INTERVAL_SECONDS`,
default 86400):

```bash
docker compose --profile backup up -d backup
```

**Verify a DB or a backup** (recommended weekly cron on the live DB):

```bash
scripts/verify_db.sh /data/axiom.db        # live DB
scripts/verify_db.sh ./backups/axiom.db.20260601T020000Z.bak   # a backup file
# weekly integrity cron:
0 3 * * 0 cd /opt/axiom && docker compose run --rm --entrypoint /scripts/verify_db.sh backup /data/axiom.db
```

**Restore** (RTO: minutes). Stop the app and any organizer/ingest writer first:

```bash
docker compose stop axiom
# pick a backup, restore it; a pre-restore safety copy is written automatically:
scripts/restore_db.sh ./backups/axiom.db.20260601T020000Z.bak /data/axiom.db
```

**Post-restore validation:**

1. The restore script already ran `PRAGMA integrity_check` and printed the
   Alembic version. If `alembic current` is behind `alembic heads`, run
   `alembic upgrade head` (the restored DB may predate a schema change).
2. Re-verify: `scripts/verify_db.sh /data/axiom.db`.
3. Start the app: `docker compose up -d axiom`.
4. Confirm health: `curl -fsS http://<host>/readyz` returns `200` (it runs
   `SELECT 1`, checks the vault is unlocked, and checks background tasks).
5. Spot-check the receipt chain via the app's verification path; the chain must
   re-derive cleanly from genesis.

### Litestream (streaming alternative)

For near-zero RPO, enable the commented-out `litestream` sidecar in
`docker-compose.yml` instead of the `backup` service. It continuously replicates
the WAL to object storage; restore with
`litestream restore -o /data/axiom.db <replica-url>`. Supply a `litestream.yml`
and cloud credentials. Use **either** Litestream **or** the cron snapshots, not
both, to avoid contending for the WAL.

## Current Production Boundary

This is suitable for a single company deployment behind HTTPS with a strong API
token, with the SQLite backups above scheduled. Before offering AXIOM as a hosted
multi-company product, add per-user identity, tenant isolation, admin RBAC, audit
identity, a managed (Postgres) database, and operational monitoring.
