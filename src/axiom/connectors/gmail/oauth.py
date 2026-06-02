from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

import requests

from axiom.connectors.base import ConnectorConfig, ConnectorState, OAuthFlow
from axiom.schema.models import new_id

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.metadata",
    "https://www.googleapis.com/auth/gmail.compose",
]


class GmailOAuth(OAuthFlow):
    authorize_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"

    def __init__(self, config: ConnectorConfig) -> None:
        scopes = config.scopes or GMAIL_SCOPES
        super().__init__(replace(config, scopes=scopes))

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.config.oauth_client_id or "",
            "redirect_uri": self.config.redirect_uri or "",
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    def exchange_code(self, code: str) -> ConnectorState:
        payload = _post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "redirect_uri": self.config.redirect_uri,
            }
        )
        return ConnectorState(
            id=new_id(),
            connector_id=self.config.id,
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            token_expires_at=_expires_at(payload),
            account_id=payload.get("email") or payload.get("account_id"),
            account_label=payload.get("email") or payload.get("account_label") or "Gmail",
            installed_by=None,
            status="connected",
        )

    def refresh(self, state: ConnectorState) -> ConnectorState:
        if state.token_expires_at is not None and state.token_expires_at > datetime.utcnow():
            return state
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
        "https://oauth2.googleapis.com/token",
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
