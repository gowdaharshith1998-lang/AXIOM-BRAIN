from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, cast

import requests

from axiom.connectors.base import ConnectorConfig, ConnectorState, OAuthFlow
from axiom.schema.models import new_id

LINEAR_SCOPES = ["read", "write", "issues:create"]
LINEAR_TOKEN_ENDPOINT = "https://api.linear.app/oauth/token"


class LinearOAuth(OAuthFlow):
    authorize_endpoint = "https://linear.app/oauth/authorize"

    def __init__(self, config: ConnectorConfig) -> None:
        scopes = config.scopes or LINEAR_SCOPES
        super().__init__(replace(config, scopes=scopes))

    def exchange_code(self, code: str) -> ConnectorState:
        payload = _post_token(
            {
                "grant_type": "authorization_code",
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            }
        )
        organization = payload.get("organization") or {}
        return ConnectorState(
            id=new_id(),
            connector_id=self.config.id,
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            token_expires_at=_expires_at(payload),
            account_id=payload.get("organization_id") or organization.get("id"),
            account_label=payload.get("account_label")
            or organization.get("name")
            or "Linear Workspace",
            installed_by=None,
            status="connected",
        )

    def refresh(self, state: ConnectorState) -> ConnectorState:
        """Rotate the Linear access token via ``grant_type=refresh_token``.

        Linear issues a ``refresh_token`` at authorization time; we exchange it
        for a fresh access token (and a possibly-rotated refresh token). When no
        refresh token is available, the existing state is returned unchanged so
        callers can surface a re-auth requirement.
        """
        if not state.refresh_token:
            return state
        payload = _post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": state.refresh_token,
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
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
        LINEAR_TOKEN_ENDPOINT,
        data=data,
        headers={"Accept": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _expires_at(payload: dict[str, Any]) -> datetime | None:
    expires_in = payload.get("expires_in")
    if expires_in is None:
        return None
    return datetime.utcnow() + timedelta(seconds=int(expires_in))
