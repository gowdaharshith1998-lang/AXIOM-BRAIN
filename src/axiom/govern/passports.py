from __future__ import annotations

import hashlib
import json
import secrets
import time
from base64 import b64decode, b64encode
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.schema.models import AgentPassport, PassportCredential
from axiom.sign.ed25519_signer import load_or_create_keypair, sign, verify
from axiom.storage.db import create_schema_table

SYSTEM_PASSPORT_ID = "demo_passport"
SYSTEM_PASSPORT_TOKEN = "demo_passport"
VERIFY_CACHE_TTL_SECONDS = 60.0
VALID_AGENT_CLASSES = {"internal", "external_mcp", "skill_runner"}
VALID_SIGNING_SCHEMES = {"demo", "ed25519", "hybrid"}

_VERIFY_CACHE: dict[str, tuple[float, AgentPassport]] = {}


class PassportError(Exception):
    pass


def _new_ulid() -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    chars: list[str] = []
    for _ in range(26):
        chars.append(alphabet[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_scope(values: list[str]) -> list[str]:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return ["*"] if "*" in cleaned else sorted(set(cleaned))


def _canonical_passport_payload(row: AgentPassport) -> dict[str, Any]:
    return {
        "passport_id": row.passport_id,
        "agent_name": row.agent_name,
        "agent_class": row.agent_class,
        "owner_email": row.owner_email,
        "scope_clusters": row.scope_clusters,
        "scope_intents": row.scope_intents,
        "scope_skills": row.scope_skills,
        "issued_at": row.issued_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "not_before": row.not_before.isoformat() if row.not_before is not None else None,
        "kill_switch": bool(row.kill_switch),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at is not None else None,
        "revocation_reason": row.revocation_reason,
        "signing_scheme": row.signing_scheme,
        "created_at": row.created_at.isoformat(),
    }


def _sign_passport(row: AgentPassport) -> str:
    canonical = json.dumps(
        _canonical_passport_payload(row),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return b64encode(sign(canonical)).decode("ascii")


_demo_signature = _sign_passport


def _verify_passport_signature(row: AgentPassport) -> bool:
    canonical = json.dumps(
        _canonical_passport_payload(row),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        signature = b64decode(row.issuer_signature, validate=True)
    except Exception:  # noqa: BLE001
        return False
    return verify(canonical, signature, load_or_create_keypair().public_key_bytes)


def _clear_cache() -> None:
    _VERIFY_CACHE.clear()


def ensure_passports_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("agent_passports"):
        create_schema_table(AgentPassport.__table__, engine)
    if not inspector.has_table("passport_credentials"):
        create_schema_table(PassportCredential.__table__, engine)


def passport_to_dict(row: AgentPassport) -> dict[str, Any]:
    return {
        "passport_id": row.passport_id,
        "agent_name": row.agent_name,
        "agent_class": row.agent_class,
        "owner_email": row.owner_email,
        "scope_clusters": row.scope_clusters,
        "scope_intents": row.scope_intents,
        "scope_skills": row.scope_skills,
        "issued_at": row.issued_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "not_before": row.not_before.isoformat() if row.not_before is not None else None,
        "kill_switch": bool(row.kill_switch),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at is not None else None,
        "revocation_reason": row.revocation_reason,
        "issuer_signature": row.issuer_signature,
        "signing_scheme": row.signing_scheme,
        "created_at": row.created_at.isoformat(),
    }


def _issue_passport_with_session(
    session: Session,
    *,
    agent_name: str,
    agent_class: str,
    owner_email: str,
    scope_clusters: list[str],
    scope_intents: list[str],
    scope_skills: list[str],
    ttl_hours: int,
    passport_id: str | None = None,
    bearer_token: str | None = None,
) -> tuple[AgentPassport, str]:
    if agent_class not in VALID_AGENT_CLASSES:
        raise ValueError(f"invalid agent_class: {agent_class!r}")
    if ttl_hours <= 0:
        raise ValueError("ttl_hours must be positive")
    now = datetime.utcnow()
    token = bearer_token or f"axiom_pt_{secrets.token_urlsafe(32)}"
    row = AgentPassport(
        passport_id=passport_id or _new_ulid(),
        agent_name=agent_name.strip(),
        agent_class=agent_class,
        owner_email=owner_email.strip(),
        scope_clusters=_normalize_scope(scope_clusters),
        scope_intents=_normalize_scope(scope_intents),
        scope_skills=_normalize_scope(scope_skills),
        issued_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
        not_before=None,
        kill_switch=False,
        revoked_at=None,
        revocation_reason=None,
        issuer_signature="",
        signing_scheme="ed25519",
        created_at=now,
    )
    row.issuer_signature = _sign_passport(row)
    session.add(row)
    session.add(
        PassportCredential(
            credential_hash=_token_hash(token),
            passport_id=row.passport_id,
            presented_count=0,
            last_presented_at=None,
            created_at=now,
        )
    )
    session.commit()
    session.refresh(row)
    _clear_cache()
    return row, token


def issue_passport(
    session_factory: sessionmaker[Session],
    *,
    agent_name: str,
    agent_class: str,
    owner_email: str,
    scope_clusters: list[str],
    scope_intents: list[str],
    scope_skills: list[str],
    ttl_hours: int,
) -> tuple[AgentPassport, str]:
    with session_factory() as session:
        return _issue_passport_with_session(
            session,
            agent_name=agent_name,
            agent_class=agent_class,
            owner_email=owner_email,
            scope_clusters=scope_clusters,
            scope_intents=scope_intents,
            scope_skills=scope_skills,
            ttl_hours=ttl_hours,
        )


def ensure_system_passport(session_factory: sessionmaker[Session]) -> AgentPassport:
    with session_factory() as session:
        row = session.get(AgentPassport, SYSTEM_PASSPORT_ID)
        if row is not None:
            session.expunge(row)
            return row
        row, _token = _issue_passport_with_session(
            session,
            agent_name="demo_system_agent",
            agent_class="internal",
            owner_email="system@axiom.local",
            scope_clusters=["*"],
            scope_intents=["*"],
            scope_skills=["*"],
            ttl_hours=24 * 365,
            passport_id=SYSTEM_PASSPORT_ID,
            bearer_token=SYSTEM_PASSPORT_TOKEN,
        )
        session.expunge(row)
        return row


def _validate_passport(row: AgentPassport) -> None:
    now = datetime.utcnow()
    if row.signing_scheme not in VALID_SIGNING_SCHEMES:
        raise PassportError("unsupported passport signing scheme")
    if row.signing_scheme in {"demo", "ed25519", "hybrid"} and not _verify_passport_signature(row):
        raise PassportError("passport signature verification failed")
    if row.not_before is not None and now < row.not_before:
        raise PassportError("passport not yet valid")
    if now >= row.expires_at:
        raise PassportError("passport expired")
    if row.revoked_at is not None:
        raise PassportError("passport revoked")
    if row.kill_switch:
        raise PassportError("passport kill switch enabled")


def verify_passport(
    session_factory: sessionmaker[Session],
    bearer_token: str,
) -> AgentPassport:
    credential_hash = _token_hash(bearer_token)
    cached = _VERIFY_CACHE.get(credential_hash)
    now_monotonic = time.monotonic()
    if cached is not None and cached[0] > now_monotonic:
        _validate_passport(cached[1])
        return cached[1]

    with session_factory() as session:
        credential = session.get(PassportCredential, credential_hash)
        if credential is None:
            raise PassportError("passport credential not found")
        row = session.get(AgentPassport, credential.passport_id)
        if row is None:
            raise PassportError("passport not found")
        _validate_passport(row)
        credential.presented_count += 1
        credential.last_presented_at = datetime.utcnow()
        session.add(credential)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    _VERIFY_CACHE[credential_hash] = (now_monotonic + VERIFY_CACHE_TTL_SECONDS, row)
    return row


def revoke_passport(
    session_factory: sessionmaker[Session],
    passport_id: str,
    reason: str | None = None,
) -> AgentPassport:
    with session_factory() as session:
        row = session.get(AgentPassport, passport_id)
        if row is None:
            raise LookupError(passport_id)
        row.revoked_at = datetime.utcnow()
        row.revocation_reason = reason or "revoked"
        row.issuer_signature = _sign_passport(row)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    _clear_cache()
    return row


def toggle_kill_switch(
    session_factory: sessionmaker[Session],
    passport_id: str,
    enabled: bool,
) -> AgentPassport:
    with session_factory() as session:
        row = session.get(AgentPassport, passport_id)
        if row is None:
            raise LookupError(passport_id)
        row.kill_switch = enabled
        row.issuer_signature = _sign_passport(row)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    _clear_cache()
    return row


def list_passports(
    session_factory: sessionmaker[Session],
    active_only: bool = True,
) -> list[AgentPassport]:
    with session_factory() as session:
        stmt = select(AgentPassport).order_by(
            AgentPassport.created_at.desc(), AgentPassport.passport_id
        )
        rows = session.execute(stmt).scalars().all()
        if active_only:
            now = datetime.utcnow()
            rows = [
                row
                for row in rows
                if row.revoked_at is None
                and not row.kill_switch
                and row.expires_at > now
                and (row.not_before is None or row.not_before <= now)
            ]
        for row in rows:
            session.expunge(row)
        return list(rows)


def get_passport(session_factory: sessionmaker[Session], passport_id: str) -> AgentPassport:
    with session_factory() as session:
        row = session.get(AgentPassport, passport_id)
        if row is None:
            raise LookupError(passport_id)
        session.expunge(row)
        return row


def check_scope(
    passport: AgentPassport,
    intent: str,
    cluster_id: str | None,
    skill_id: str | None = None,
) -> bool:
    clusters = set(passport.scope_clusters or [])
    intents = set(passport.scope_intents or [])
    skills = set(passport.scope_skills or [])
    cluster_ok = "*" in clusters or (cluster_id is not None and cluster_id in clusters)
    intent_ok = "*" in intents or intent in intents
    skill_ok = "*" in skills or skill_id is None or skill_id in skills
    return cluster_ok and intent_ok and skill_ok
