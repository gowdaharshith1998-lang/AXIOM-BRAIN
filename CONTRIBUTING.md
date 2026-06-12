# Contributing

Thanks for improving AXIOM Brain. This repository is a full-stack Python/TypeScript system, so good contributions keep backend, frontend, documentation, and operational behavior in sync.

## Development Setup

Prerequisites:

- Python 3.13
- `uv`
- Node.js 22 and npm

Install backend dependencies:

```bash
uv sync --frozen --extra dev
```

Install frontend dependencies:

```bash
cd frontend
npm ci
```

## Local Development

Run the backend API and WebSocket server:

```bash
uv run axiom serve --host 127.0.0.1 --port 8000
```

Run with live synthetic events:

```bash
uv run axiom serve --host 127.0.0.1 --port 8000 --live
```

Run the frontend:

```bash
cd frontend
npm run dev
```

## Required Checks

Run backend checks before opening a PR:

```bash
uv lock --check
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv run mypy
uv run pytest -q --maxfail=5 --cov=axiom --cov-report=xml --cov-fail-under=50
```

Run frontend checks for UI or client changes:

```bash
cd frontend
npm audit --audit-level=moderate
npm test
npm run lint
npm run build
```

The frontend lint script is a TypeScript no-emit static check. The production build also runs TypeScript project build mode before Vite bundling.

## Pull Request Expectations

- Keep each PR focused on one behavior, cleanup, or documentation theme.
- Separate mechanical refactors from behavior changes.
- Add or update tests for behavior changes.
- Update README/docs when setup, security posture, deployment, or user-facing behavior changes.
- Include screenshots or short clips for visual frontend changes.
- Call out any checks that could not be run locally.

## Security-Sensitive Changes

Changes touching auth, vault storage, connector OAuth, webhook verification, signing, policy enforcement, receipts, or production config need extra care:

- Prefer failing closed over permissive fallback.
- Never print or commit plaintext secrets.
- Preserve auditability of signed actions and receipts.
- Add regression tests for bypasses, replay handling, missing config, and invalid signatures.
