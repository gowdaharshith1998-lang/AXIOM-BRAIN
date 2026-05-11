from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

import requests  # type: ignore[import-untyped]

from axiom.connectors.base import ConnectorEvent, WebhookHandler

API = "https://gmail.googleapis.com/gmail/v1"


class GmailWebhookHandler(WebhookHandler):
    def __init__(self, verifier: Callable[[str], bool] | None = None) -> None:
        self.verifier = verifier or _default_verify_google_jwt

    def verify(self, request: Any) -> bool:
        auth = _headers(request).get("authorization", "")
        if not auth.startswith("Bearer "):
            return False
        return bool(self.verifier(auth.removeprefix("Bearer ").strip()))

    def parse(self, request: Any) -> list[ConnectorEvent]:
        payload = _payload(request)
        message = payload.get("message") or {}
        data_raw = str(message.get("data") or "")
        decoded = json.loads(base64.urlsafe_b64decode(_pad_b64(data_raw)).decode("utf-8"))
        email = str(decoded.get("emailAddress") or "me")
        history_id = str(decoded["historyId"])
        return [
            ConnectorEvent(
                vendor="gmail",
                event_type="history.available",
                external_id=f"{email}:{history_id}",
                payload=decoded,
                timestamp=datetime.utcnow(),
                signature_ok=self.verify(request),
            )
        ]

    def fetch_history(self, state: Any, event: ConnectorEvent) -> list[dict[str, Any]]:
        history_id = str(event.payload["historyId"])
        response = requests.get(
            f"{API}/users/me/history",
            params={"startHistoryId": history_id},
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {state.access_token}",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        return list(payload.get("history", []))


def _default_verify_google_jwt(_token: str) -> bool:
    return False


def _payload(request: Any) -> dict[str, Any]:
    body = getattr(request, "body", b"")
    if callable(body):
        body = body()
    if isinstance(body, str):
        body = body.encode("utf-8")
    return cast(dict[str, Any], json.loads(bytes(body).decode("utf-8")))


def _headers(request: Any) -> dict[str, str]:
    raw = getattr(request, "headers", {}) or {}
    return {str(key).lower(): str(value) for key, value in raw.items()}


def _pad_b64(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return padded.encode("utf-8")
