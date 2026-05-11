from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from axiom.connectors.base import ConnectorEvent, HmacSha256WebhookHandler


class LinearWebhookHandler(HmacSha256WebhookHandler):
    def __init__(self, secret: str) -> None:
        super().__init__("linear", secret, header_name="linear-signature")

    def parse(self, request: Any) -> list[ConnectorEvent]:
        headers = {
            str(key).lower(): str(value)
            for key, value in getattr(request, "headers", {}).items()
        }
        body = getattr(request, "body", b"")
        if callable(body):
            body = body()
        payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else str(body))
        event_type = str(payload.get("type") or "unknown")
        action = payload.get("action")
        if action:
            event_type = f"{event_type}.{action}"
        data = payload.get("data") or {}
        external_id = headers.get("linear-delivery") or str(data.get("id") or event_type)
        return [
            ConnectorEvent(
                vendor="linear",
                event_type=event_type,
                external_id=external_id,
                payload=payload,
                timestamp=datetime.utcnow(),
                signature_ok=self.verify(request),
            )
        ]
