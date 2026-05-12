from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from axiom.schema.models import LLMProviderKey
from axiom.storage.db import create_schema_table, get_session
from axiom.vault.crypto import ENV_VAR
from axiom.vault.errors import VaultCorrupt, VaultLocked

Provider = Literal["anthropic", "groq", "mistral", "openai"]
TestStatus = Literal["valid", "invalid", "untested"]

VALID_PROVIDERS: Final[frozenset[str]] = frozenset({"anthropic", "groq", "mistral", "openai"})
VALID_TEST_STATUSES: Final[frozenset[str]] = frozenset({"valid", "invalid", "untested"})
_HTTP_TIMEOUT = 5.0


class UnknownLLMProvider(ValueError):  # noqa: N818
    pass


class LLMProviderKeyNotFound(LookupError):  # noqa: N818
    pass


@dataclass(frozen=True, slots=True)
class LLMProviderKeyMetadata:
    provider: str
    key_fingerprint: str
    connected_at: datetime
    last_tested_at: datetime | None
    last_test_status: str
    demo_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "key_fingerprint": self.key_fingerprint,
            "connected_at": self.connected_at.isoformat(),
            "last_tested_at": self.last_tested_at.isoformat()
            if self.last_tested_at is not None
            else None,
            "last_test_status": self.last_test_status,
            "demo_flag": self.demo_flag,
        }


def _validate_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in VALID_PROVIDERS:
        raise UnknownLLMProvider(f"unknown LLM provider: {provider!r}")
    return normalized


def _fernet() -> Fernet:
    raw = os.environ.get(ENV_VAR)
    if not raw:
        raise VaultLocked(f"{ENV_VAR} is not set")
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise VaultLocked(f"{ENV_VAR} is malformed") from exc


def _encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def _decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise VaultCorrupt("stored LLM provider key cannot be decrypted") from exc


def _metadata(row: LLMProviderKey) -> LLMProviderKeyMetadata:
    return LLMProviderKeyMetadata(
        provider=row.provider,
        key_fingerprint=row.key_fingerprint,
        connected_at=row.connected_at,
        last_tested_at=row.last_tested_at,
        last_test_status=row.last_test_status,
        demo_flag=row.demo_flag,
    )


def ensure_llm_provider_keys_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("llm_provider_keys"):
        create_schema_table(LLMProviderKey.__table__, engine)


def set_provider_key_with_session(
    session: Session,
    provider: str,
    plaintext_key: str,
    *,
    demo_flag: bool = False,
) -> LLMProviderKeyMetadata:
    normalized = _validate_provider(provider)
    plaintext = plaintext_key.strip()
    if not plaintext:
        raise ValueError("key must not be empty")
    now = datetime.utcnow()
    row = session.get(LLMProviderKey, normalized)
    if row is None:
        row = LLMProviderKey(provider=normalized, connected_at=now)
    row.encrypted_key = _encrypt(plaintext)
    row.key_fingerprint = plaintext[-4:]
    row.connected_at = now
    row.last_tested_at = None
    row.last_test_status = "untested"
    row.demo_flag = demo_flag
    session.add(row)
    session.commit()
    session.refresh(row)
    return _metadata(row)


def get_provider_key_metadata_with_session(
    session: Session,
    provider: str,
) -> LLMProviderKeyMetadata:
    normalized = _validate_provider(provider)
    row = session.get(LLMProviderKey, normalized)
    if row is None:
        raise LLMProviderKeyNotFound(normalized)
    return _metadata(row)


def list_provider_key_metadata_with_session(session: Session) -> list[LLMProviderKeyMetadata]:
    rows = session.execute(select(LLMProviderKey).order_by(LLMProviderKey.provider)).scalars().all()
    return [_metadata(row) for row in rows]


def delete_provider_key_with_session(session: Session, provider: str) -> bool:
    normalized = _validate_provider(provider)
    row = session.get(LLMProviderKey, normalized)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def get_provider_key_plaintext_with_session(session: Session, provider: str) -> str:
    normalized = _validate_provider(provider)
    row = session.get(LLMProviderKey, normalized)
    if row is None:
        raise LLMProviderKeyNotFound(normalized)
    return _decrypt(row.encrypted_key)


def _models_request(provider: str, key: str) -> httpx.Response:
    if provider == "anthropic":
        return httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=_HTTP_TIMEOUT,
        )
    urls = {
        "openai": "https://api.openai.com/v1/models",
        "groq": "https://api.groq.com/openai/v1/models",
        "mistral": "https://api.mistral.ai/v1/models",
    }
    return httpx.get(
        urls[provider],
        headers={"Authorization": f"Bearer {key}"},
        timeout=_HTTP_TIMEOUT,
    )


def test_provider_connection_with_session(
    session: Session,
    provider: str,
) -> LLMProviderKeyMetadata:
    normalized = _validate_provider(provider)
    row = session.get(LLMProviderKey, normalized)
    if row is None:
        raise LLMProviderKeyNotFound(normalized)
    plaintext = _decrypt(row.encrypted_key)
    try:
        response = _models_request(normalized, plaintext)
        status: TestStatus = "valid" if 200 <= response.status_code < 300 else "invalid"
    except httpx.HTTPError:
        status = "invalid"
    row.last_tested_at = datetime.utcnow()
    row.last_test_status = status
    session.add(row)
    session.commit()
    session.refresh(row)
    return _metadata(row)


def set_provider_key(provider: str, plaintext_key: str) -> LLMProviderKeyMetadata:
    session = get_session()
    try:
        return set_provider_key_with_session(session, provider, plaintext_key)
    finally:
        session.close()


def get_provider_key_metadata(provider: str) -> LLMProviderKeyMetadata:
    session = get_session()
    try:
        return get_provider_key_metadata_with_session(session, provider)
    finally:
        session.close()


def test_provider_connection(provider: str) -> LLMProviderKeyMetadata:
    session = get_session()
    try:
        return test_provider_connection_with_session(session, provider)
    finally:
        session.close()
