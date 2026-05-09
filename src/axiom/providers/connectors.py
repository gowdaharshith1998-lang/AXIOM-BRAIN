"""verify_key implementations for connector credentials (sync httpx)."""

from __future__ import annotations

import logging

import httpx

from axiom.providers.models import VerifyResult

_LOG = logging.getLogger(__name__)

_HTTP_TIMEOUT = 5.0

_GITHUB_USER = "https://api.github.com/user"
_LINEAR_GQL = "https://api.linear.app/graphql"
_NOTION_ME = "https://api.notion.com/v1/users/me"
_SLACK_AUTH_TEST = "https://slack.com/api/auth.test"


def _ensure_api_key_string(plaintext: str | dict) -> VerifyResult | str:
    if isinstance(plaintext, dict):
        return VerifyResult(status="auth_error", detail="expected string API token")
    key = plaintext.strip()
    if not key:
        return VerifyResult(status="auth_error", detail="empty token")
    return key


def _map_http_code(status_code: int) -> VerifyResult | None:
    if status_code == 429:
        return VerifyResult(status="rate_limited", detail="rate limited")
    if status_code in (401, 403):
        return VerifyResult(status="auth_error", detail="unauthorized")
    return None


def verify_github_key(plaintext: str | dict) -> VerifyResult:
    got = _ensure_api_key_string(plaintext)
    if isinstance(got, VerifyResult):
        return got
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            r = client.get(
                _GITHUB_USER,
                headers={"Authorization": f"Bearer {got}"},
            )
    except httpx.TimeoutException:
        _LOG.debug("github verify timeout")
        return VerifyResult(status="network_error", detail="timeout")
    except httpx.RequestError as exc:
        _LOG.debug("github verify network error: %s", type(exc).__name__)
        return VerifyResult(status="network_error", detail="network error")

    if r.status_code == 200:
        return VerifyResult(status="ok")
    special = _map_http_code(r.status_code)
    if special:
        return special
    return VerifyResult(
        status="network_error",
        detail=f"unexpected HTTP status {r.status_code}",
    )


def verify_linear_key(plaintext: str | dict) -> VerifyResult:
    got = _ensure_api_key_string(plaintext)
    if isinstance(got, VerifyResult):
        return got
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            r = client.post(
                _LINEAR_GQL,
                headers={
                    "Authorization": got,
                    "Content-Type": "application/json",
                },
                json={"query": "{viewer{id}}"},
            )
    except httpx.TimeoutException:
        _LOG.debug("linear verify timeout")
        return VerifyResult(status="network_error", detail="timeout")
    except httpx.RequestError as exc:
        _LOG.debug("linear verify network error: %s", type(exc).__name__)
        return VerifyResult(status="network_error", detail="network error")

    if r.status_code == 200:
        return VerifyResult(status="ok")
    special = _map_http_code(r.status_code)
    if special:
        return special
    return VerifyResult(
        status="network_error",
        detail=f"unexpected HTTP status {r.status_code}",
    )


def verify_notion_key(plaintext: str | dict) -> VerifyResult:
    got = _ensure_api_key_string(plaintext)
    if isinstance(got, VerifyResult):
        return got
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            r = client.get(
                _NOTION_ME,
                headers={
                    "Authorization": f"Bearer {got}",
                    "Notion-Version": "2022-06-28",
                },
            )
    except httpx.TimeoutException:
        _LOG.debug("notion verify timeout")
        return VerifyResult(status="network_error", detail="timeout")
    except httpx.RequestError as exc:
        _LOG.debug("notion verify network error: %s", type(exc).__name__)
        return VerifyResult(status="network_error", detail="network error")

    if r.status_code == 200:
        return VerifyResult(status="ok")
    special = _map_http_code(r.status_code)
    if special:
        return special
    return VerifyResult(
        status="network_error",
        detail=f"unexpected HTTP status {r.status_code}",
    )


def verify_slack_key(plaintext: str | dict) -> VerifyResult:
    got = _ensure_api_key_string(plaintext)
    if isinstance(got, VerifyResult):
        return got
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            r = client.post(
                _SLACK_AUTH_TEST,
                headers={"Authorization": f"Bearer {got}"},
            )
    except httpx.TimeoutException:
        _LOG.debug("slack verify timeout")
        return VerifyResult(status="network_error", detail="timeout")
    except httpx.RequestError as exc:
        _LOG.debug("slack verify network error: %s", type(exc).__name__)
        return VerifyResult(status="network_error", detail="network error")

    if r.status_code != 200:
        special = _map_http_code(r.status_code)
        if special:
            return special
        return VerifyResult(
            status="network_error",
            detail=f"unexpected HTTP status {r.status_code}",
        )

    try:
        body = r.json()
    except ValueError:
        return VerifyResult(status="network_error", detail="invalid JSON response")

    if body.get("ok") is True:
        return VerifyResult(status="ok")
    # Slack returns HTTP 200 with ok=false on invalid auth.
    return VerifyResult(status="auth_error", detail="slack auth.test failed")
