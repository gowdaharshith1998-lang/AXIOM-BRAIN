# Security Policy

## Supported Versions

The default branch is the active development line. Tagged releases beginning with `v0.2.0` represent the current production-hardening baseline.

## Reporting a Vulnerability

Please do not open a public issue for suspected vulnerabilities.

Preferred reporting path:

1. Use GitHub private vulnerability reporting from the repository Security tab, if enabled.
2. If private vulnerability reporting is unavailable, contact the repository owner directly through GitHub before public disclosure.

Include:

- Affected commit, tag, or deployment version.
- Steps to reproduce.
- Expected and actual impact.
- Any logs, request examples, or proof-of-concept details that do not expose live secrets.
- Suggested mitigation, if known.

## Security Scope

High-priority areas include:

- API and WebSocket authentication.
- Connector OAuth state, webhook signatures, and token refresh.
- Fernet vault storage and plaintext secret handling.
- AXIOM signing keys, receipts, and policy enforcement.
- Production fail-closed configuration.
- Dependency, container, and GitHub Actions supply-chain security.

## Operational Guidance

- Rotate any credential suspected of exposure.
- Keep `AXIOM_VAULT_KEY`, provider keys, OAuth secrets, and API tokens out of git.
- Enable Dependabot alerts, secret scanning, push protection, and CodeQL/default code scanning in GitHub settings where available.
- Use `AXIOM_ENV=production`, `AXIOM_AUTH_REQUIRED=1`, and a strong `AXIOM_API_TOKEN` before exposing a deployment.
