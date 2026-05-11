from __future__ import annotations

import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True, slots=True)
class ConnectorConfig:
    id: str
    vendor: str
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    redirect_uri: str | None = None
    scopes: list[str] = field(default_factory=list)
    webhook_secret: str | None = None
    workspace_id: str | None = None
    install_state: str = "not_installed"


@dataclass(frozen=True, slots=True)
class ConnectorState:
    id: str
    connector_id: str
    access_token: str
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    account_id: str | None = None
    account_label: str | None = None
    installed_by: str | None = None
    status: str = "connected"


@dataclass(frozen=True, slots=True)
class ConnectorEvent:
    vendor: str
    event_type: str
    external_id: str
    payload: dict[str, Any]
    timestamp: datetime
    signature_ok: bool


class OAuthFlow(ABC):
    authorize_endpoint: str = ""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.config.oauth_client_id or "",
            "redirect_uri": self.config.redirect_uri or "",
            "scope": " ".join(self.config.scopes),
            "state": state,
        }
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    @abstractmethod
    def exchange_code(self, code: str) -> ConnectorState: ...

    @abstractmethod
    def refresh(self, state: ConnectorState) -> ConnectorState: ...


class WebhookHandler(ABC):
    @abstractmethod
    def verify(self, request: Any) -> bool: ...

    @abstractmethod
    def parse(self, request: Any) -> list[ConnectorEvent]: ...


class HmacSha256WebhookHandler(WebhookHandler):
    def __init__(self, vendor: str, secret: str, *, header_name: str) -> None:
        self.vendor = vendor
        self.secret = secret
        self.header_name = header_name.lower()

    def verify(self, request: Any) -> bool:
        header = _headers(request).get(self.header_name, "")
        if not header:
            return False
        expected = hmac.new(self.secret.encode("utf-8"), _body(request), "sha256").hexdigest()
        actual = header.removeprefix("sha256=")
        return hmac.compare_digest(actual, expected)

    def parse(self, request: Any) -> list[ConnectorEvent]:
        return []


class Connector(ABC):
    config: ConnectorConfig
    oauth: OAuthFlow
    webhook: WebhookHandler
    ingestor: Any
    writer: Any

    @abstractmethod
    def test_connection(self) -> dict[str, Any]: ...


def _headers(request: Any) -> dict[str, str]:
    raw = getattr(request, "headers", {}) or {}
    return {str(key).lower(): str(value) for key, value in raw.items()}


def _body(request: Any) -> bytes:
    body = getattr(request, "body", b"")
    if callable(body):
        body = body()
    if isinstance(body, str):
        return body.encode("utf-8")
    return bytes(body)
