from __future__ import annotations

import re
from typing import Any, cast

import requests

API = "https://slack.com/api"
MENTION_RE = re.compile(r"<@(?P<user_id>[A-Z0-9]+)>")


def fetch_channels(state: Any) -> list[dict[str, Any]]:
    return _get_paginated(
        "conversations.list",
        state.access_token,
        "channels",
        {"types": "public_channel,private_channel", "exclude_archived": "true", "limit": "200"},
    )


def fetch_users(state: Any) -> list[dict[str, Any]]:
    return _get_paginated("users.list", state.access_token, "members", {"limit": "200"})


def fetch_recent_messages_per_channel(
    state: Any,
    channel_id: str,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return _get_paginated(
        "conversations.history",
        state.access_token,
        "messages",
        {"channel": channel_id, "limit": str(limit)},
    )


def normalize_channel(channel: dict[str, Any]) -> dict[str, Any]:
    channel_id = str(channel["id"])
    name = str(channel.get("name") or "")
    return {
        "nick": f"channel:{channel_id}",
        "type": "channel",
        "source_id": f"slack:channel:{channel_id}",
        "cluster_id": _cluster_for_channel(name),
        "data": {"vendor": "slack", **channel},
    }


def normalize_user(user: dict[str, Any]) -> dict[str, Any]:
    user_id = str(user["id"])
    return {
        "nick": f"person:{user_id}",
        "type": "person",
        "source_id": f"slack:user:{user_id}",
        "cluster_id": "people",
        "data": {"vendor": "slack", **user},
    }


def normalize_message(channel_id: str, message: dict[str, Any]) -> dict[str, Any]:
    timestamp = str(message["ts"])
    return {
        "nick": f"message:{channel_id}:{timestamp}",
        "type": "message",
        "source_id": f"slack:message:{channel_id}:{timestamp}",
        "cluster_id": "comms",
        "data": {"vendor": "slack", "channel": channel_id, **message},
    }


def channel_to_message_edge(channel_nick: str, message_nick: str) -> dict[str, Any]:
    return {
        "source_nick": channel_nick,
        "target_nick": message_nick,
        "relationship": "channel_has_message",
        "data": {},
    }


def thread_parent_child_edge(parent_nick: str, reply_nick: str) -> dict[str, Any]:
    return {
        "source_nick": parent_nick,
        "target_nick": reply_nick,
        "relationship": "thread_has_reply",
        "data": {},
    }


def message_mention_edges(message_nick: str, text: str) -> list[dict[str, Any]]:
    return [
        {
            "source_nick": message_nick,
            "target_nick": f"person:{match.group('user_id')}",
            "relationship": "message_mentions_person",
            "data": {},
        }
        for match in MENTION_RE.finditer(text)
    ]


def _get_paginated(
    method: str,
    token: str,
    key: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    cursor: str | None = None
    rows: list[dict[str, Any]] = []
    while True:
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        payload = _get(method, token, query)
        rows.extend(payload.get(key, []))
        cursor = str(payload.get("response_metadata", {}).get("next_cursor") or "")
        if not cursor:
            return rows


def _get(method: str, token: str, params: dict[str, str]) -> dict[str, Any]:
    response = requests.get(
        f"{API}/{method}",
        params=params,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    if not payload.get("ok", True):
        raise ValueError(str(payload.get("error", f"slack api failed: {method}")))
    return payload


def _cluster_for_channel(name: str) -> str:
    normalized = name.lower()
    if any(part in normalized for part in ("eng", "dev", "platform", "ops")):
        return "engineering_code"
    if any(part in normalized for part in ("sales", "customer", "gtm")):
        return "customers"
    return "comms"
