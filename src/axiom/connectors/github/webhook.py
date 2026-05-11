from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from axiom.connectors.base import ConnectorEvent, HmacSha256WebhookHandler


class GitHubWebhookHandler(HmacSha256WebhookHandler):
    def __init__(self, secret: str) -> None:
        super().__init__("github", secret, header_name="X-Hub-Signature-256")

    def parse(self, request: Any) -> list[ConnectorEvent]:
        headers = {
            str(key).lower(): str(value)
            for key, value in getattr(request, "headers", {}).items()
        }
        event_name = headers.get("x-github-event", "unknown")
        delivery = headers.get("x-github-delivery", "")
        body = getattr(request, "body", b"")
        if callable(body):
            body = body()
        payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else str(body))
        action = payload.get("action")
        event_type = f"{event_name}.{action}" if action else event_name
        external_id = delivery or _external_id(event_name, payload)
        return [
            ConnectorEvent(
                vendor="github",
                event_type=event_type,
                external_id=external_id,
                payload=payload,
                timestamp=datetime.utcnow(),
                signature_ok=self.verify(request),
            )
        ]


def _external_id(event_name: str, payload: dict[str, Any]) -> str:
    repo = payload.get("repository") or {}
    repo_name = repo.get("full_name") or "unknown"
    item = payload.get("issue") or payload.get("pull_request") or payload.get("release") or {}
    item_id = item.get("id") or payload.get("after") or "unknown"
    return f"{repo_name}:{event_name}:{item_id}"
