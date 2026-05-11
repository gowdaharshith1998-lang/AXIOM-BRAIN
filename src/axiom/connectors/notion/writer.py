from __future__ import annotations

from typing import Any

import requests  # type: ignore[import-untyped]
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors.notion.poller import API, NOTION_VERSION
from axiom.connectors.writer import ConnectorWriter
from axiom.policy import ActionRequest


class NotionWriter(ConnectorWriter):
    def __init__(
        self,
        *,
        state: Any | None = None,
        session_factory: sessionmaker[Session] | None = None,
        policy_evaluator: Any | None = None,
    ) -> None:
        super().__init__(
            vendor="notion",
            session_factory=session_factory,
            policy_evaluator=policy_evaluator,
        )
        self.state = state

    def _perform_execute(self, action: ActionRequest, decision: Any) -> Any:
        del decision
        method, path, payload = _request_for_action(action)
        response = requests.request(
            method,
            f"{API}{path}",
            json=payload,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {getattr(self.state, 'access_token', '')}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_VERSION,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()


def _request_for_action(action: ActionRequest) -> tuple[str, str, dict[str, Any]]:
    if action.intent == "update_page":
        return (
            "PATCH",
            f"/pages/{action.payload['page_id']}",
            {"properties": action.payload["properties"]},
        )
    if action.intent == "create_page":
        return (
            "POST",
            "/pages",
            {
                "parent": action.payload["parent"],
                "properties": action.payload["properties"],
                **_optional(action.payload, "children"),
            },
        )
    if action.intent == "add_comment":
        return (
            "POST",
            "/comments",
            {
                "parent": {"page_id": action.payload["page_id"]},
                "rich_text": action.payload["rich_text"],
            },
        )
    if action.intent == "archive_page":
        return ("PATCH", f"/pages/{action.payload['page_id']}", {"archived": True})
    raise ValueError(f"unsupported Notion intent: {action.intent}")


def _optional(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}
