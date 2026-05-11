from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

import requests  # type: ignore[import-untyped]
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors.writer import ConnectorWriter
from axiom.policy import ActionRequest

API = "https://gmail.googleapis.com/gmail/v1"


class GmailWriter(ConnectorWriter):
    def __init__(
        self,
        *,
        state: Any | None = None,
        session_factory: sessionmaker[Session] | None = None,
        policy_evaluator: Any | None = None,
    ) -> None:
        super().__init__(
            vendor="gmail",
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
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()


def _request_for_action(action: ActionRequest) -> tuple[str, str, dict[str, Any]]:
    if action.intent == "send_email":
        return ("POST", "/users/me/messages/send", {"raw": _raw_message(action.payload)})
    if action.intent == "reply":
        return (
            "POST",
            "/users/me/messages/send",
            {"raw": _raw_message(action.payload), "threadId": action.payload["thread_id"]},
        )
    if action.intent == "mark_read":
        return (
            "POST",
            f"/users/me/messages/{action.payload['message_id']}/modify",
            {"removeLabelIds": ["UNREAD"]},
        )
    if action.intent == "label":
        return (
            "POST",
            f"/users/me/messages/{action.payload['message_id']}/modify",
            {"addLabelIds": action.payload["label_ids"]},
        )
    if action.intent == "archive":
        return (
            "POST",
            f"/users/me/messages/{action.payload['message_id']}/modify",
            {"removeLabelIds": ["INBOX"]},
        )
    raise ValueError(f"unsupported Gmail intent: {action.intent}")


def _raw_message(payload: dict[str, Any]) -> str:
    if "raw" in payload:
        return str(payload["raw"])
    message = EmailMessage()
    message["To"] = str(payload["to"])
    if "from" in payload:
        message["From"] = str(payload["from"])
    if "subject" in payload:
        message["Subject"] = str(payload["subject"])
    message.set_content(str(payload.get("body", "")))
    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8").rstrip("=")
