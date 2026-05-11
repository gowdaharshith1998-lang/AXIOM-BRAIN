from __future__ import annotations

from dataclasses import replace
from typing import Any

import requests  # type: ignore[import-untyped]

from axiom.connectors.base import ConnectorConfig, ConnectorState, OAuthFlow
from axiom.schema.models import new_id

LINEAR_SCOPES = ["read", "write", "issues:create"]


class LinearOAuth(OAuthFlow):
    authorize_endpoint = "https://linear.app/oauth/authorize"

    def __init__(self, config: ConnectorConfig) -> None:
        scopes = config.scopes or LINEAR_SCOPES
        super().__init__(replace(config, scopes=scopes))

    def exchange_code(self, code: str) -> ConnectorState:
        response = requests.post(
            "https://api.linear.app/oauth/token",
            data={
                "grant_type": "authorization_code",
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
        organization = payload.get("organization") or {}
        return ConnectorState(
            id=new_id(),
            connector_id=self.config.id,
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            token_expires_at=None,
            account_id=payload.get("organization_id") or organization.get("id"),
            account_label=payload.get("account_label")
            or organization.get("name")
            or "Linear Workspace",
            installed_by=None,
            status="connected",
        )

    def refresh(self, state: ConnectorState) -> ConnectorState:
        return state
