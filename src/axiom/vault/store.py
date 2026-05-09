"""CRUD for encrypted secrets.

Two layers:

  * Lower-level functions (``_*_with_session``) take an explicit ``Session``.
    They are reused by the public API and by tests that supply their own
    session fixture.

  * Public helpers (:func:`store_secret`, :func:`get_secret`, etc.) open + close
    a session via :func:`axiom.storage.db.get_session`, mirroring the pattern in
    ``axiom/storage/__init__.py``.

Plaintext discipline:

  * :func:`get_secret` is the ONLY function that returns plaintext.
  * :func:`store_secret` is the only function that accepts plaintext.
  * Everything else operates on metadata only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from axiom.storage.db import get_session
from axiom.vault import crypto
from axiom.vault.errors import DuplicateSecret
from axiom.vault.models import VALID_STATUSES, Secret, SecretMetadataDTO, SecretStatus


def _get_row(session: Session, provider_id: str, key_name: str) -> Secret | None:
    stmt = select(Secret).where(
        Secret.provider_id == provider_id,
        Secret.key_name == key_name,
    )
    return session.execute(stmt).scalar_one_or_none()


def store_secret_with_session(
    session: Session,
    provider_id: str,
    key_name: str,
    plaintext: str,
) -> SecretMetadataDTO:
    """Encrypt ``plaintext`` and persist a new ``Secret`` row.

    Raises:
        VaultLocked: if the master key is not available.
        DuplicateSecret: if ``(provider_id, key_name)`` already exists.
    """
    ciphertext = crypto.encrypt(plaintext)
    row = Secret(
        provider_id=provider_id,
        key_name=key_name,
        encrypted_value=ciphertext,
        status="untested",
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateSecret(
            f"a secret already exists for provider_id={provider_id!r} "
            f"key_name={key_name!r}; delete it first if you want to replace it"
        ) from exc
    session.refresh(row)
    return SecretMetadataDTO.model_validate(row)


def get_secret_with_session(
    session: Session,
    provider_id: str,
    key_name: str,
) -> str:
    """Decrypt and return the plaintext value for ``(provider_id, key_name)``.

    THE ONLY PLAINTEXT EXIT POINT. Do not log the return value. Pass it directly
    to whatever needs it (e.g. an HTTP client) and let it go out of scope.

    Raises:
        VaultLocked: if the master key is not available.
        VaultCorrupt: if decryption fails (rotated key / tampered row).
        KeyError: if no secret matches.
    """
    row = _get_row(session, provider_id, key_name)
    if row is None:
        raise KeyError(f"no secret for provider_id={provider_id!r} key_name={key_name!r}")
    return crypto.decrypt(row.encrypted_value)


def list_secrets_with_session(
    session: Session,
    provider_id: str | None = None,
) -> list[SecretMetadataDTO]:
    """Return metadata for every stored secret. Never returns plaintext.

    Safe to call when the vault is locked — does not touch the master key.
    """
    stmt = select(Secret)
    if provider_id is not None:
        stmt = stmt.where(Secret.provider_id == provider_id)
    stmt = stmt.order_by(Secret.provider_id, Secret.key_name)
    rows = session.execute(stmt).scalars().all()
    return [SecretMetadataDTO.model_validate(r) for r in rows]


def delete_secret_with_session(
    session: Session,
    provider_id: str,
    key_name: str,
) -> bool:
    """Delete the row for ``(provider_id, key_name)``. Returns True if a row was deleted.

    Safe to call when the vault is locked — does not touch the master key.
    """
    row = _get_row(session, provider_id, key_name)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def mark_tested_with_session(
    session: Session,
    provider_id: str,
    key_name: str,
    status: SecretStatus,
    *,
    when: datetime | None = None,
) -> SecretMetadataDTO:
    """Update ``status`` + ``last_tested_at`` after a verification attempt.

    Phase 5.13.0 just records the result; the verifier itself ships in 5.13.1.

    Safe to call when the vault is locked — does not touch the master key.

    Raises:
        ValueError: if ``status`` is not one of the four canonical values.
        KeyError: if no secret matches.
    """
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; must be one of {sorted(VALID_STATUSES)}"
        )
    row = _get_row(session, provider_id, key_name)
    if row is None:
        raise KeyError(f"no secret for provider_id={provider_id!r} key_name={key_name!r}")
    row.status = status
    row.last_tested_at = when or datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return SecretMetadataDTO.model_validate(row)


# ─── public, session-managed wrappers ───────────────────────────────────────


def store_secret(provider_id: str, key_name: str, plaintext: str) -> SecretMetadataDTO:
    session = get_session()
    try:
        return store_secret_with_session(session, provider_id, key_name, plaintext)
    finally:
        session.close()


def get_secret(provider_id: str, key_name: str) -> str:
    """THE ONLY PLAINTEXT EXIT POINT. See :func:`get_secret_with_session`."""
    session = get_session()
    try:
        return get_secret_with_session(session, provider_id, key_name)
    finally:
        session.close()


def list_secrets(provider_id: str | None = None) -> list[SecretMetadataDTO]:
    session = get_session()
    try:
        return list_secrets_with_session(session, provider_id)
    finally:
        session.close()


def delete_secret(provider_id: str, key_name: str) -> bool:
    session = get_session()
    try:
        return delete_secret_with_session(session, provider_id, key_name)
    finally:
        session.close()


def mark_tested(
    provider_id: str,
    key_name: str,
    status: SecretStatus,
    *,
    when: datetime | None = None,
) -> SecretMetadataDTO:
    session = get_session()
    try:
        return mark_tested_with_session(session, provider_id, key_name, status, when=when)
    finally:
        session.close()
