from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import requests

from axiom.connectors.base import ConnectorState, OAuthFlow
from axiom.schema.models import new_id


class NotionOAuth(OAuthFlow):
    authorize_endpoint = "https://api.notion.com/v1/oauth/authorize"

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.config.oauth_client_id or "",
            "redirect_uri": self.config.redirect_uri or "",
            "response_type": "code",
            "owner": "user",
            "state": state,
        }
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    def exchange_code(self, code: str) -> ConnectorState:
        response = requests.post(
            "https://api.notion.com/v1/oauth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            },
            auth=(self.config.oauth_client_id or "", self.config.oauth_client_secret or ""),
            headers={"Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return ConnectorState(
            id=new_id(),
            connector_id=self.config.id,
            access_token=str(payload["access_token"]),
            refresh_token=None,
            token_expires_at=None,
            account_id=payload.get("workspace_id"),
            account_label=payload.get("workspace_name") or "Notion Workspace",
            installed_by=None,
            status="connected",
        )

    def refresh(self, state: ConnectorState) -> ConnectorState:
        return state
