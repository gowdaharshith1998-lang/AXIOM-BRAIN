from __future__ import annotations

from email.utils import parseaddr
from typing import Any, cast

import requests  # type: ignore[import-untyped]

API = "https://gmail.googleapis.com/gmail/v1"


def fetch_labels(state: Any) -> list[dict[str, Any]]:
    return list(_get(state.access_token, "/users/me/labels").get("labels", []))


def fetch_threads(state: Any) -> list[dict[str, Any]]:
    return list(_get(state.access_token, "/users/me/threads").get("threads", []))


def fetch_messages_in_thread(state: Any, thread_id: str) -> list[dict[str, Any]]:
    return list(_get(state.access_token, f"/users/me/threads/{thread_id}").get("messages", []))


def normalize_label(label: dict[str, Any]) -> dict[str, Any]:
    label_id = str(label["id"])
    return {
        "nick": f"label:{label_id}",
        "type": "label",
        "source_id": f"gmail:label:{label_id}",
        "cluster_id": "comms",
        "data": {"vendor": "gmail", **label},
    }


def normalize_thread(thread: dict[str, Any]) -> dict[str, Any]:
    thread_id = str(thread["id"])
    return {
        "nick": f"email_thread:{thread_id}",
        "type": "email_thread",
        "source_id": f"gmail:thread:{thread_id}",
        "cluster_id": "comms",
        "data": {"vendor": "gmail", **thread},
    }


def normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    message_id = str(message["id"])
    headers = _headers(message)
    return {
        "nick": f"email:{message_id}",
        "type": "email",
        "source_id": f"gmail:message:{message_id}",
        "cluster_id": "comms",
        "data": {
            "vendor": "gmail",
            "from": parseaddr(headers.get("from", ""))[1] or headers.get("from"),
            "to": headers.get("to"),
            "subject": headers.get("subject"),
            **message,
        },
    }


def thread_to_message_edge(thread_nick: str, message_nick: str) -> dict[str, Any]:
    return {
        "source_nick": thread_nick,
        "target_nick": message_nick,
        "relationship": "thread_has_message",
        "data": {},
    }


def message_to_participant_edge(message_nick: str, participant_nick: str) -> dict[str, Any]:
    return {
        "source_nick": message_nick,
        "target_nick": participant_nick,
        "relationship": "message_has_participant",
        "data": {},
    }


def message_to_attachment_edge(message_nick: str, attachment_nick: str) -> dict[str, Any]:
    return {
        "source_nick": message_nick,
        "target_nick": attachment_nick,
        "relationship": "message_has_attachment",
        "data": {},
    }


def _get(token: str, path: str) -> dict[str, Any]:
    response = requests.get(
        f"{API}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _headers(message: dict[str, Any]) -> dict[str, str]:
    headers = (message.get("payload") or {}).get("headers") or []
    return {str(row.get("name", "")).lower(): str(row.get("value", "")) for row in headers}
