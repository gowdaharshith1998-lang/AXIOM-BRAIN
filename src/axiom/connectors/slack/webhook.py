from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any, cast

from axiom.connectors.base import ConnectorEvent, WebhookHandler

REPLAY_WINDOW_SECONDS = 60 * 5


class SlackWebhookHandler(WebhookHandler):
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def verify(self, request: Any) -> bool:
        headers = _headers(request)
        signature = headers.get("x-slack-signature", "")
        timestamp_raw = headers.get("x-slack-request-timestamp", "")
        if not signature or not timestamp_raw:
            return False
        try:
            timestamp = int(timestamp_raw)
        except ValueError:
            return False
        if abs(_now() - timestamp) > REPLAY_WINDOW_SECONDS:
            return False
        basestring = b"v0:" + str(timestamp).encode() + b":" + _body(request)
        expected = (
            "v0="
            + hmac.new(
                self.secret.encode("utf-8"),
                basestring,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(signature, expected)

    def challenge_response(self, request: Any) -> str | None:
        payload = _payload(request)
        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            return str(challenge) if challenge is not None else None
        return None

    def parse(self, request: Any) -> list[ConnectorEvent]:
        payload = _payload(request)
        event = payload.get("event") or payload
        event_type = str(event.get("type") or "unknown")
        return [
            ConnectorEvent(
                vendor="slack",
                event_type=event_type,
                external_id=_external_id(event_type, event),
                payload=payload,
                timestamp=datetime.utcnow(),
                signature_ok=self.verify(request),
            )
        ]


def _external_id(event_type: str, event: dict[str, Any]) -> str:
    channel = event.get("channel") or (event.get("item") or {}).get("channel") or "unknown"
    timestamp = event.get("ts") or (event.get("item") or {}).get("ts") or event.get("event_ts")
    if timestamp is None:
        return f"{channel}:{event_type}"
    if event_type == "reaction_added":
        return f"{channel}:{timestamp}:reaction_added"
    return f"{channel}:{timestamp}"


def _payload(request: Any) -> dict[str, Any]:
    body = _body(request)
    return cast(dict[str, Any], json.loads(body.decode("utf-8")))


def _headers(request: Any) -> dict[str, str]:
    raw = getattr(request, "headers", {}) or {}
    return {str(key).lower(): str(value) for key, value in raw.items()}


def _body(request: Any) -> bytes:
    body = getattr(request, "body", b"")
    if callable(body):
        body = body()
    if isinstance(body, str):
        return body.encode("utf-8")
    return bytes(body)


def _now() -> int:
    return int(time.time())
