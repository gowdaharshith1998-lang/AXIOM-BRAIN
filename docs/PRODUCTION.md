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

The container serves the FastAPI API, `/ws/brain`, and the built React frontend
from one origin.

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

## Current Production Boundary

This is suitable for a single company deployment behind HTTPS with a strong API
token. Before offering AXIOM as a hosted multi-company product, add per-user
identity, tenant isolation, admin RBAC, audit identity, managed database backups,
and operational monitoring.
