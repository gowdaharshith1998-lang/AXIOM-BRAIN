from __future__ import annotations

from dataclasses import replace

import requests

from axiom.connectors.base import ConnectorConfig, ConnectorState, OAuthFlow
from axiom.schema.models import new_id

GITHUB_SCOPES = ["repo", "read:org", "write:discussion"]


class GitHubOAuth(OAuthFlow):
    authorize_endpoint = "https://github.com/login/oauth/authorize"

    def __init__(self, config: ConnectorConfig) -> None:
        scopes = config.scopes or GITHUB_SCOPES
        super().__init__(replace(config, scopes=scopes))

    def exchange_code(self, code: str) -> ConnectorState:
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        return ConnectorState(
            id=new_id(),
            connector_id=self.config.id,
            access_token=str(payload["access_token"]),
            refresh_token=None,
            token_expires_at=None,
            account_id=payload.get("account_id"),
            account_label=payload.get("account_label") or "GitHub",
            installed_by=None,
            status="connected",
        )

    def refresh(self, state: ConnectorState) -> ConnectorState:
        """No-op: GitHub OAuth access tokens do not expire.

        GitHub App user-to-server tokens *can* expire, but the OAuth App tokens
        this connector mints are non-expiring and carry no refresh token, so the
        existing state is returned unchanged.
        """
        return state
