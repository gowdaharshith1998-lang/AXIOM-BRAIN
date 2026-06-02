from __future__ import annotations

import base64
import hmac
import os
from collections.abc import Mapping

from fastapi import Request, WebSocket

API_TOKEN_ENV = "AXIOM_API_TOKEN"
AUTH_REQUIRED_ENV = "AXIOM_AUTH_REQUIRED"
AUTH_DISABLED_ENV = "AXIOM_AUTH_DISABLED"
ALLOW_WS_QUERY_TOKEN_ENV = "AXIOM_ALLOW_WS_QUERY_TOKEN"
WS_AUTH_SUBPROTOCOL = "axiom.auth"
WS_AUTH_TOKEN_PREFIX = "axiom-token."

# Liveness/readiness probes are exempt: load balancers, orchestrators, and the
# docker-compose healthcheck cannot attach bearer tokens. They expose only
# coarse operational state (status + failed-check names), no data.
_EXEMPT_HTTP_PATHS = {"/api/health", "/readyz", "/livez"}
_CONNECTOR_ROUTE_PREFIX = "/api/internal/connectors/"
# Everything under these prefixes requires auth even for GET/HEAD. Any other
# GET/HEAD path can only ever reach the SPA StaticFiles mount (P1-8): the SPA
# bundle is a public artifact (secrets are entered by the user into the
# TokenGate at runtime), so serving it unauthenticated is by design — without
# this the browser gets a 401 JSON body instead of the app and the user can
# never reach the token prompt.
_PROTECTED_GET_PREFIXES = ("/api", "/ws", "/metrics")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def configured_api_token() -> str | None:
    token = os.environ.get(API_TOKEN_ENV, "").strip()
    return token or None


def _is_production() -> bool:
    return os.environ.get("AXIOM_ENV", "").strip().lower() == "production"


def auth_required() -> bool:
    """Fail-closed by default (P0-2 / GOV-AUTH-001).

    Precedence, highest first:
      1. production            → always required
      2. AXIOM_API_TOKEN set   → required (enforce the configured token)
      3. AXIOM_AUTH_REQUIRED   → required
      4. AXIOM_AUTH_DISABLED   → disabled (local dev opt-out only; ignored in prod)
      5. default               → required (closed)
    """
    if _is_production():
        return True
    if configured_api_token() is not None:
        return True
    if _truthy(os.environ.get(AUTH_REQUIRED_ENV)):
        return True
    if _truthy(os.environ.get(AUTH_DISABLED_ENV)):
        return False
    return True


def auth_is_misconfigured() -> bool:
    return auth_required() and configured_api_token() is None


def is_http_auth_exempt(method: str, path: str) -> bool:
    if method.upper() == "OPTIONS":
        return True
    if path in _EXEMPT_HTTP_PATHS:
        return True
    if path.startswith(_CONNECTOR_ROUTE_PREFIX) and (
        path.endswith("/callback") or path.endswith("/webhook")
    ):
        return True
    # SPA static assets (P1-8): read-only requests outside the protected API /
    # WS / metrics surface can only ever hit the StaticFiles mount at "/".
    if method.upper() in {"GET", "HEAD"} and not path.startswith(_PROTECTED_GET_PREFIXES):
        return True
    return False


def _candidate_token(
    headers: Mapping[str, str],
    query: Mapping[str, str] | None = None,
) -> str | None:
    auth_header = headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip()
        if bearer:
            return bearer

    api_key = headers.get("x-axiom-api-key", "").strip()
    if api_key:
        return api_key

    subprotocol_token = _candidate_subprotocol_token(headers)
    if subprotocol_token:
        return subprotocol_token

    if query is not None and _truthy(os.environ.get(ALLOW_WS_QUERY_TOKEN_ENV)):
        token = query.get("token", "").strip()
        if token:
            return token

    return None


def _websocket_protocols(headers: Mapping[str, str]) -> list[str]:
    raw = headers.get("sec-websocket-protocol", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _candidate_subprotocol_token(headers: Mapping[str, str]) -> str | None:
    protocols = _websocket_protocols(headers)
    for index, protocol in enumerate(protocols[:-1]):
        if protocol == WS_AUTH_SUBPROTOCOL:
            return _decode_subprotocol_token(protocols[index + 1])
    return None


def _decode_subprotocol_token(protocol: str) -> str | None:
    if not protocol.startswith(WS_AUTH_TOKEN_PREFIX):
        return protocol
    encoded = protocol.removeprefix(WS_AUTH_TOKEN_PREFIX)
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def token_is_valid(candidate: str | None) -> bool:
    expected = configured_api_token()
    if expected is None or candidate is None:
        return False
    return hmac.compare_digest(candidate, expected)


def request_is_authenticated(request: Request) -> bool:
    return token_is_valid(_candidate_token(request.headers))


def websocket_is_authenticated(websocket: WebSocket) -> bool:
    return token_is_valid(_candidate_token(websocket.headers, websocket.query_params))


def websocket_auth_subprotocol(websocket: WebSocket) -> str | None:
    return (
        WS_AUTH_SUBPROTOCOL
        if WS_AUTH_SUBPROTOCOL in _websocket_protocols(websocket.headers)
        else None
    )
