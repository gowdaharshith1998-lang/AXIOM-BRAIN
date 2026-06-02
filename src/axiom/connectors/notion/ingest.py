from __future__ import annotations

from typing import Any, cast

import requests

from axiom.connectors.notion.poller import API, NOTION_VERSION


def fetch_databases(state: Any) -> list[dict[str, Any]]:
    response = requests.post(
        f"{API}/search",
        json={"filter": {"property": "object", "value": "database"}},
        headers=_headers(state.access_token),
        timeout=15,
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    return list(payload.get("results", []))


def fetch_pages_in_database(state: Any, database_id: str) -> list[dict[str, Any]]:
    response = requests.post(
        f"{API}/databases/{database_id}/query",
        json={},
        headers=_headers(state.access_token),
        timeout=15,
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    return list(payload.get("results", []))


def fetch_blocks(state: Any, block_id: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{API}/blocks/{block_id}/children",
        headers=_headers(state.access_token),
        timeout=15,
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    return list(payload.get("results", []))


def normalize_database(database: dict[str, Any]) -> dict[str, Any]:
    database_id = str(database["id"])
    return {
        "nick": f"database:{database_id}",
        "type": "database",
        "source_id": f"notion:database:{database_id}",
        "cluster_id": "knowledge",
        "data": {"vendor": "notion", **database},
    }


def normalize_page(page: dict[str, Any]) -> dict[str, Any]:
    page_id = str(page["id"])
    return {
        "nick": f"document:{page_id}",
        "type": "document",
        "source_id": f"notion:page:{page_id}",
        "cluster_id": "knowledge",
        "data": {"vendor": "notion", **page},
    }


def database_to_page_edge(database_nick: str, page_nick: str) -> dict[str, Any]:
    return {
        "source_nick": database_nick,
        "target_nick": page_nick,
        "relationship": "database_has_page",
        "data": {},
    }


def page_to_subpage_edge(page_nick: str, subpage_nick: str) -> dict[str, Any]:
    return {
        "source_nick": page_nick,
        "target_nick": subpage_nick,
        "relationship": "page_has_subpage",
        "data": {},
    }


def mention_to_linked_page_edge(page_nick: str, linked_page_nick: str) -> dict[str, Any]:
    return {
        "source_nick": page_nick,
        "target_nick": linked_page_nick,
        "relationship": "page_mentions_page",
        "data": {},
    }


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
