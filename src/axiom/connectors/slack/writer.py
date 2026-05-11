from __future__ import annotations

from typing import Any

import requests  # type: ignore[import-untyped]
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors.writer import ConnectorWriter
from axiom.policy import ActionRequest

API = "https://slack.com/api"


class SlackWriter(ConnectorWriter):
    def __init__(
        self,
        *,
        state: Any | None = None,
        session_factory: sessionmaker[Session] | None = None,
        policy_evaluator: Any | None = None,
    ) -> None:
        super().__init__(
            vendor="slack",
            session_factory=session_factory,
            policy_evaluator=policy_evaluator,
        )
        self.state = state

    def _perform_execute(self, action: ActionRequest, decision: Any) -> Any:
        del decision
        method, payload = _method_payload(action)
        response = requests.post(
            f"{API}/{method}",
            json=payload,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {getattr(self.state, 'access_token', '')}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=15,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        if not result.get("ok", True):
            raise ValueError(str(result.get("error", f"slack api failed: {method}")))
        return result


def _method_payload(action: ActionRequest) -> tuple[str, dict[str, Any]]:
    if action.intent == "post_message":
        return (
            "chat.postMessage",
            {
                "channel": action.payload["channel"],
                "text": action.payload["text"],
                **_optional(action.payload, "thread_ts", "blocks", "metadata"),
            },
        )
    if action.intent == "update_message":
        return (
            "chat.update",
            {
                "channel": action.payload["channel"],
                "ts": action.payload["timestamp"],
                "text": action.payload["text"],
                **_optional(action.payload, "blocks"),
            },
        )
    if action.intent == "reaction_add":
        return (
            "reactions.add",
            {
                "channel": action.payload["channel"],
                "timestamp": action.payload["timestamp"],
                "name": action.payload["name"],
            },
        )
    if action.intent == "invite":
        return (
            "conversations.invite",
            {
                "channel": action.payload["channel"],
                "users": action.payload["users"],
            },
        )
    raise ValueError(f"unsupported Slack intent: {action.intent}")


def _optional(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}
