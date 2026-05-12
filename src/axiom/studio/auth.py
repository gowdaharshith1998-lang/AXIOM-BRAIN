from __future__ import annotations

import base64
import hmac
import os
from collections.abc import Mapping

from fastapi import Request, WebSocket

API_TOKEN_ENV = "AXIOM_API_TOKEN"
AUTH_REQUIRED_ENV = "AXIOM_AUTH_REQUIRED"
ALLOW_WS_QUERY_TOKEN_ENV = "AXIOM_ALLOW_WS_QUERY_TOKEN"
WS_AUTH_SUBPROTOCOL = "axiom.auth"
WS_AUTH_TOKEN_PREFIX = "axiom-token."

_EXEMPT_HTTP_PATHS = {"/api/health"}
_CONNECTOR_ROUTE_PREFIX = "/api/internal/connectors/"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def configured_api_token() -> str | None:
    token = os.environ.get(API_TOKEN_ENV, "").strip()
    return token or None


def auth_required() -> bool:
    return (
        configured_api_token() is not None
        or _truthy(os.environ.get(AUTH_REQUIRED_ENV))
        or os.environ.get("AXIOM_ENV", "").strip().lower() == "production"
    )


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
