"""Pydantic models for provider metadata and verification results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

VerifyStatus = Literal[
    "ok",
    "auth_error",
    "network_error",
    "rate_limited",
    "not_implemented",
]

ProviderKind = Literal["llm", "connector", "oauth"]


class VerifyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: VerifyStatus
    detail: str | None = None


class CredentialField(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    secret: bool = False


class ProviderMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    kind: ProviderKind
    credential_shape: tuple[CredentialField, ...]
    docs_url: str
    verify_endpoint: str
    env_var_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
