from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import requests  # type: ignore[import-untyped]

from axiom.connectors.base import ConnectorEvent

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionPoller:
    interval_seconds = 60

    def __init__(
        self,
        *,
        state: Any,
        last_seen: dict[str, str] | None = None,
    ) -> None:
        self.state = state
        self.last_seen = dict(last_seen or {})

    def poll_once(self) -> list[ConnectorEvent]:
        pages = _search_changed_pages(self.state.access_token)
        events: list[ConnectorEvent] = []
        for page in pages:
            page_id = str(page["id"])
            edited_at = str(page.get("last_edited_time") or "")
            if self.last_seen.get(page_id) == edited_at:
                continue
            self.last_seen[page_id] = edited_at
            events.append(
                ConnectorEvent(
                    vendor="notion",
                    event_type="page.changed",
                    external_id=page_id,
                    payload=page,
                    timestamp=datetime.utcnow(),
                    signature_ok=True,
                )
            )
        return events


def _search_changed_pages(token: str) -> list[dict[str, Any]]:
    response = requests.post(
        f"{API}/search",
        json={"filter": {"property": "object", "value": "page"}},
        headers=_headers(token),
        timeout=15,
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    return list(payload.get("results", []))


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
