"""ORM model + DTO for the encrypted secrets vault.

The Secret table is registered against the same ``Base`` as the rest of the
schema so a single ``Base.metadata`` reaches alembic. ``alembic/env.py``
imports this module to ensure the table is part of ``target_metadata``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from axiom.schema.models import Base, new_id

SecretStatus = Literal["untested", "valid", "invalid", "expired"]

VALID_STATUSES: Final[frozenset[str]] = frozenset({"untested", "valid", "invalid", "expired"})


class Secret(Base):
    """An encrypted credential.

    Plaintext NEVER lives in this row — only the Fernet ciphertext does. Decrypting
    requires the ``AXIOM_VAULT_KEY`` master key in the environment.
    """

    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("provider_id", "key_name", name="uq_secrets_provider_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(String(64), index=True)
    key_name: Mapped[str] = mapped_column(String(128))
    encrypted_value: Mapped[str] = mapped_column(String(8192))
    status: Mapped[str] = mapped_column(String(16), default="untested", index=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SecretMetadataDTO(BaseModel):
    """Metadata-only view of a secret. NEVER includes ``encrypted_value`` or plaintext.

    Returned by :func:`axiom.vault.list_secrets`. Safe to log, serialize, send
    over an API boundary.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str
    key_name: str
    status: str
    last_tested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
