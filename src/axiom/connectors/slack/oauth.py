from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

import requests

from axiom.connectors.base import ConnectorConfig, ConnectorState, OAuthFlow
from axiom.schema.models import new_id

SLACK_TOKEN_ENDPOINT = "https://slack.com/api/oauth.v2.access"

SLACK_BOT_SCOPES = [
    "channels:history",
    "channels:read",
    "chat:write",
    "groups:read",
    "im:read",
    "users:read",
]
SLACK_USER_SCOPES = ["search:read"]


class SlackOAuth(OAuthFlow):
    authorize_endpoint = "https://slack.com/oauth/v2/authorize"

    def __init__(self, config: ConnectorConfig) -> None:
        scopes = config.scopes or SLACK_BOT_SCOPES
        super().__init__(replace(config, scopes=scopes))

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.config.oauth_client_id or "",
            "redirect_uri": self.config.redirect_uri or "",
            "scope": ",".join(self.config.scopes),
            "user_scope": ",".join(SLACK_USER_SCOPES),
            "state": state,
        }
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    def exchange_code(self, code: str) -> ConnectorState:
        payload = _post_token(
            {
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            }
        )
        team = payload.get("team") or {}
        return ConnectorState(
            id=new_id(),
            connector_id=self.config.id,
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            token_expires_at=_expires_at(payload),
            account_id=payload.get("team_id") or team.get("id"),
            account_label=payload.get("account_label") or team.get("name") or "Slack Workspace",
            installed_by=None,
            status="connected",
        )

    def refresh(self, state: ConnectorState) -> ConnectorState:
        """Rotate the Slack bot token via ``grant_type=refresh_token``.

        Slack token rotation is opt-in per app; when enabled the install
        response carries a ``refresh_token`` and a short-lived ``access_token``
        with an ``expires_in``. We exchange the refresh token for a fresh
        access/refresh pair through ``oauth.v2.access``. When no refresh token is
        present (rotation disabled / legacy non-expiring token) the state is
        returned unchanged.
        """
        if not state.refresh_token:
            return state
        payload = _post_token(
            {
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": state.refresh_token,
            }
        )
        return replace(
            state,
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token") or state.refresh_token,
            token_expires_at=_expires_at(payload),
        )


def _post_token(data: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        SLACK_TOKEN_ENDPOINT,
        data=data,
        headers={"Accept": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    payload = cast(dict[str, Any], response.json())
    if not payload.get("ok", True):
        raise ValueError(str(payload.get("error", "slack oauth failed")))
    return payload


def _expires_at(payload: dict[str, Any]) -> datetime | None:
    expires_in = payload.get("expires_in")
    if expires_in is None:
        return None
    return datetime.utcnow() + timedelta(seconds=int(expires_in))
