from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt
from axiom.schema.models import ApprovalRequest, new_id

ApprovalEventCallback = Callable[[str, dict[str, Any]], None]
SessionFactory = Callable[[], Session]


def ensure_approvals_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("approval_requests"):
        ApprovalRequest.__table__.create(bind=engine, checkfirst=True)
        return
    indexes = {index["name"] for index in inspector.get_indexes("approval_requests")}
    for index in ApprovalRequest.__table__.indexes:
        if index.name not in indexes:
            index.create(bind=engine, checkfirst=True)


def approval_to_dict(row: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "action_id": row.action_id,
        "agent_name": row.agent_name,
        "passport_id": row.passport_id,
        "intent": row.intent,
        "target_entity_id": row.target_entity_id,
        "proposed_action": row.proposed_action or {},
        "policy_id": row.policy_id,
        "reason": row.reason,
        "guidance": row.guidance,
        "required_role": row.required_role,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at is not None else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at is not None else None,
        "resolved_by": row.resolved_by,
        "resolution_note": row.resolution_note,
        "resume_token": row.resume_token,
    }


def create_approval_request(
    session_factory: SessionFactory,
    action: Any,
    passport: Any,
    decision: Any,
    *,
    event_callback: ApprovalEventCallback | None = None,
) -> ApprovalRequest:
    now = datetime.utcnow()
    timeout = int(getattr(decision, "approval_timeout_seconds", None) or 1800)
    proposed_action = {
        "proposed_action": getattr(action, "proposed_action", ""),
        "payload": getattr(action, "payload", {}) or {},
        "idempotency_key": getattr(action, "idempotency_key", None),
    }
    with session_factory() as session:
        row = ApprovalRequest(
            id=new_id(),
            action_id=getattr(action, "idempotency_key", None) or f"approval:{new_id()}",
            agent_name=str(getattr(action, "agent_name", "")),
            passport_id=getattr(passport, "passport_id", None),
            intent=str(getattr(action, "intent", "")),
            target_entity_id=getattr(action, "target_entity_id", None),
            proposed_action=proposed_action,
            policy_id=str(getattr(decision, "policy_id", "")),
            reason=str(getattr(decision, "reason", "")),
            guidance=getattr(decision, "guidance", None),
            required_role=getattr(decision, "approval_required_role", None) or "ops",
            status="pending",
            created_at=now,
            expires_at=now + timedelta(seconds=timeout),
            resume_token=new_id(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        payload = approval_to_dict(row)
    if event_callback is not None:
        event_callback("approval_requested", payload)
    return row


def list_pending_approvals(
    session_factory: SessionFactory,
    filter_by_role: str | None = None,
    *,
    status: str = "pending",
) -> list[ApprovalRequest]:
    with session_factory() as session:
        stmt = select(ApprovalRequest).where(ApprovalRequest.status == status)
        if filter_by_role is not None:
            stmt = stmt.where(ApprovalRequest.required_role == filter_by_role)
        stmt = stmt.order_by(ApprovalRequest.created_at, ApprovalRequest.id)
        return list(session.execute(stmt).scalars().all())


def approve_request(
    session_factory: SessionFactory,
    request_id: str,
    *,
    by_user: str,
    note: str | None = None,
    event_callback: ApprovalEventCallback | None = None,
) -> ApprovalRequest:
    row = _resolve_request(session_factory, request_id, "approved", by_user, note)
    if event_callback is not None:
        event_callback("approval_approved", approval_to_dict(row))
    return row


def deny_request(
    session_factory: SessionFactory,
    request_id: str,
    *,
    by_user: str,
    note: str | None = None,
    event_callback: ApprovalEventCallback | None = None,
) -> ApprovalRequest:
    row = _resolve_request(session_factory, request_id, "denied", by_user, note)
    _chain_resolution_receipt(session_factory, row, "deny", note or "approval denied")
    if event_callback is not None:
        event_callback("approval_denied", approval_to_dict(row))
    return row


def expire_old_requests(session_factory: SessionFactory) -> list[ApprovalRequest]:
    now = datetime.utcnow()
    expired: list[ApprovalRequest] = []
    with session_factory() as session:
        rows = session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.status == "pending")
            .where(ApprovalRequest.expires_at <= now)
        ).scalars().all()
        for row in rows:
            row.status = "expired"
            row.resolved_at = now
            row.resolution_note = "approval expired"
            session.add(row)
            expired.append(row)
        session.commit()
        for row in expired:
            session.refresh(row)
    for row in expired:
        _chain_resolution_receipt(session_factory, row, "expired", "approval expired")
    return expired


def get_approval(session_factory: SessionFactory, request_id: str) -> ApprovalRequest:
    with session_factory() as session:
        row = session.get(ApprovalRequest, request_id)
        if row is None:
            raise LookupError(request_id)
        return row


def _resolve_request(
    session_factory: SessionFactory,
    request_id: str,
    status: str,
    by_user: str,
    note: str | None,
) -> ApprovalRequest:
    if not by_user:
        raise ValueError("by_user is required")
    with session_factory() as session:
        row = session.get(ApprovalRequest, request_id)
        if row is None:
            raise LookupError(request_id)
        if row.status != "pending":
            raise ValueError(f"approval is already {row.status}")
        row.status = status
        row.resolved_at = datetime.utcnow()
        row.resolved_by = by_user
        row.resolution_note = note
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def _chain_resolution_receipt(
    session_factory: SessionFactory,
    row: ApprovalRequest,
    decision: str,
    reason: str,
) -> None:
    chain_insert_receipt(
        session_factory,
        ReceiptInsert(
            id=f"approval_receipt_{new_id()}",
            action_id=f"approval:{row.id}:{decision}",
            agent_name=row.agent_name,
            intent=row.intent,
            target_entity_id=row.target_entity_id,
            cluster_id=None,
            decision=decision,
            reason=reason,
            policy_id=row.policy_id,
            guidance=row.guidance,
            suggested_alternative=None,
            signing_scheme="ed25519",
            signature="",
            passport_id=row.passport_id,
            demo_flag=False,
        ),
    )
