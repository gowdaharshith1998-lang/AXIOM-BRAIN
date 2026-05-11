# Connectors

AXIOM connector support is feature-flagged per vendor and defaults off. Enable only the
vendors you are actively configuring:

```bash
AXIOM_CONNECTOR_GITHUB_ENABLED=1
AXIOM_CONNECTOR_LINEAR_ENABLED=1
AXIOM_CONNECTOR_SLACK_ENABLED=1
AXIOM_CONNECTOR_NOTION_ENABLED=1
AXIOM_CONNECTOR_GMAIL_ENABLED=1
```

Each connector follows the same path:

1. OAuth install stores a row in `connector_states`.
2. Initial sync normalizes vendor objects into the existing ingest pipeline.
3. Webhooks or polling write raw rows to `connector_events` and publish `/ws/brain` events.
4. Writes are proposed as `ActionRequest`s by a vendor writer.
5. `ConnectorWriter.execute()` evaluates policy and chains receipts before any vendor API call.

## OAuth Apps

Configure redirect URIs to match the backend callback endpoints:

| Vendor | Redirect URI | Client env |
| --- | --- | --- |
| GitHub | `/api/internal/connectors/github/callback` | `AXIOM_GITHUB_CLIENT_ID`, `AXIOM_GITHUB_CLIENT_SECRET` |
| Linear | `/api/internal/connectors/linear/callback` | `AXIOM_LINEAR_CLIENT_ID`, `AXIOM_LINEAR_CLIENT_SECRET` |
| Slack | `/api/internal/connectors/slack/callback` | `AXIOM_SLACK_CLIENT_ID`, `AXIOM_SLACK_CLIENT_SECRET` |
| Notion | `/api/internal/connectors/notion/callback` | `AXIOM_NOTION_CLIENT_ID`, `AXIOM_NOTION_CLIENT_SECRET` |
| Gmail | `/api/internal/connectors/gmail/callback` | `AXIOM_GMAIL_CLIENT_ID`, `AXIOM_GMAIL_CLIENT_SECRET` |

The frontend starts installs with `POST /api/internal/connectors/{vendor}/install`, opens the
returned `authorize_url`, then relies on the callback to persist the token.

## Scopes

Scopes are intentionally narrow but include write scopes because connector writers must be able to
execute approved actions.

| Vendor | Required scopes | Why |
| --- | --- | --- |
| GitHub | `repo`, `read:org`, `write:discussion` | Read repositories, issues, pull requests, and write comments, labels, closes, merges. |
| Linear | `read`, `write`, `issues:create` | Read teams, projects, issues, and perform issue comments, state changes, assignments, creation. |
| Slack | Bot: `channels:history`, `channels:read`, `chat:write`, `groups:read`, `im:read`, `users:read`; user: `search:read` | Read public/private channel context where installed, map users/messages, and post approved messages or reactions. |
| Notion | Notion integration capabilities for reading pages/databases and inserting/updating blocks/pages | Read workspace content through search and write approved page/block updates. |
| Gmail | `gmail.readonly`, `gmail.send` | Read thread/message context and send approved mail actions. |

## Webhooks And Polling

GitHub, Linear, Slack, and Gmail use webhook-style watch paths. Notion uses polling because public
Notion webhooks are not assumed in this tier.

| Vendor | Endpoint | Secret env | Notes |
| --- | --- | --- | --- |
| GitHub | `/api/internal/connectors/github/webhook` | `AXIOM_GITHUB_WEBHOOK_SECRET` | Verifies `X-Hub-Signature-256`; parses issue, comment, pull request, review, push, release events. |
| Linear | `/api/internal/connectors/linear/webhook` | `AXIOM_LINEAR_WEBHOOK_SECRET` | Verifies `linear-signature`; parses issue, comment, project, cycle events. |
| Slack | `/api/internal/connectors/slack/webhook` | `AXIOM_SLACK_SIGNING_SECRET` | Verifies v0 Slack signatures and timestamp replay window; handles URL verification. |
| Gmail | `/api/internal/connectors/gmail/webhook` | Google Pub/Sub JWT verifier config | Parses Pub/Sub history notifications and can fetch changed history. |
| Notion | `/api/internal/connectors/notion/sync` | None | Polls search results and page/block deltas through the sync path. |

Raw events are available through `GET /api/internal/connectors/{vendor}/events` and aggregate
status through `GET /api/internal/connectors/status`.

## Writer Policy Flow

Connector writers never call vendor write APIs directly from UI or webhook code. The required flow is:

1. Build an action with `writer.propose_action(intent, payload)`.
2. Pass the action to `writer.execute(action, passport=...)`.
3. `ConnectorWriter` calls the active `RealPolicyEvaluator`.
4. If policy returns `allow`, or an approval decision carries `approval_id`, the writer executes the vendor API call.
5. If policy returns `deny`, `correct`, or `pause` without an approval id, execution is blocked with
   `ConnectorWriteBlocked`.
6. Every allow or block chains a `Receipt` with `agent_name="connector:{vendor}"`.

This keeps connector writes inside the same governance and receipt chain as other AXIOM actions.

## Testing Recipes

Run connector-focused backend tests with:

```bash
PYTHONPATH=src pytest tests/test_connectors_framework.py tests/test_github_connector.py \
  tests/test_linear_connector.py tests/test_slack_connector.py tests/test_notion_connector.py \
  tests/test_gmail_connector.py tests/test_connectors_e2e_smoke.py -q
```

Run the connector UI tests with:

```bash
npm test -- connectors-page.test.tsx
```

Vendor HTTP is mocked with `responses`; tests must not make real network calls. For local manual
checks, use the feature flag for one vendor, configure its OAuth and webhook env vars, install from
`/settings/connectors`, then use `Sync Now`, `Test`, and `Events` from the connector row.
