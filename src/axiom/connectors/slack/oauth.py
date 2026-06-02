from __future__ import annotations

from dataclasses import replace
from typing import Any
from urllib.parse import urlencode

import requests

from axiom.connectors.base import ConnectorConfig, ConnectorState, OAuthFlow
from axiom.schema.models import new_id

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
        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        if not payload.get("ok", True):
            raise ValueError(str(payload.get("error", "slack oauth failed")))
        team = payload.get("team") or {}
        authed_user = payload.get("authed_user") or {}
        return ConnectorState(
            id=new_id(),
            connector_id=self.config.id,
            access_token=str(payload["access_token"]),
            refresh_token=authed_user.get("access_token"),
            token_expires_at=None,
            account_id=payload.get("team_id") or team.get("id"),
            account_label=payload.get("account_label") or team.get("name") or "Slack Workspace",
            installed_by=None,
            status="connected",
        )

    def refresh(self, state: ConnectorState) -> ConnectorState:
        return state
