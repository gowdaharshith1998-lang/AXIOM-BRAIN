from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import Engine, desc, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.demo_flag import is_demo_target
from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt
from axiom.govern.watchdog_rules import DEFAULT_RULES, WatchdogRule
from axiom.schema.models import Entity, WatchdogAlert
from axiom.storage.db import create_schema_table, schema_table_indexes

logger = logging.getLogger("axiom.govern.watchdog")

WATCHDOG_AGENT_NAME = "watchdog"
WATCHDOG_PASSPORT_ID = "demo_passport"
ALERT_STATUSES = {"open", "acknowledged", "resolved"}
SEVERITY_RANK = {"critical": 3, "warning": 2, "info": 1}


class _Broadcaster(Protocol):
    @property
    def current_seq(self) -> int: ...
    async def publish(self, envelope: dict[str, Any]) -> int: ...
    def subscribe(self, *, since: int = 0) -> Any: ...


SessionFactory = Callable[[], Session]

_registered_rules: list[WatchdogRule] = list(DEFAULT_RULES)


def ensure_watchdog_alerts_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("watchdog_alerts"):
        create_schema_table(WatchdogAlert.__table__, engine)
        return
    columns = {column["name"] for column in inspector.get_columns("watchdog_alerts")}
    expected = {
        "alert_id",
        "entity_id",
        "rule_id",
        "severity",
        "reason",
        "evidence",
        "suggested_action",
        "status",
        "detected_at",
        "resolved_at",
        "resolved_by",
        "demo_flag",
    }
    if not expected.issubset(columns):
        return
    indexes = {index["name"] for index in inspector.get_indexes("watchdog_alerts")}
    for index in schema_table_indexes(WatchdogAlert.__table__):
        if index.name not in indexes:
            index.create(bind=engine, checkfirst=True)


def register_rule(rule: WatchdogRule) -> None:
    if rule not in _registered_rules:
        _registered_rules.append(rule)


def alert_to_dict(alert: WatchdogAlert) -> dict[str, Any]:
    return {
        "alert_id": alert.alert_id,
        "entity_id": alert.entity_id,
        "rule_id": alert.rule_id,
        "severity": alert.severity,
        "reason": alert.reason,
        "evidence": alert.evidence or {},
        "suggested_action": alert.suggested_action,
        "status": alert.status,
        "detected_at": alert.detected_at.isoformat() if alert.detected_at is not None else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at is not None else None,
        "resolved_by": alert.resolved_by,
        "demo_flag": alert.demo_flag,
    }


def watchdog_insight_from_alert(alert: WatchdogAlert) -> dict[str, Any]:
    timestamp = (
        alert.detected_at.isoformat()
        if alert.detected_at is not None
        else datetime.utcnow().isoformat()
    )
    return {
        "insight_id": alert.alert_id,
        "severity": alert.severity,
        "message": alert.reason,
        "confidence": 1.0,
        "related_entity_ids": [alert.entity_id],
        "recommended_actions": [alert.suggested_action],
        "timestamp": timestamp,
        "demo": alert.demo_flag,
        "alert": alert_to_dict(alert),
    }


def _existing_active_alert(session: Session, entity_id: str, rule_id: str) -> WatchdogAlert | None:
    return session.execute(
        select(WatchdogAlert)
        .where(
            WatchdogAlert.entity_id == entity_id,
            WatchdogAlert.rule_id == rule_id,
            WatchdogAlert.status.in_(["open", "acknowledged"]),
        )
        .order_by(desc(WatchdogAlert.detected_at), desc(WatchdogAlert.alert_id))
        .limit(1)
    ).scalar_one_or_none()


def detect_for_entity(
    session: Session,
    entity_id: str,
    *,
    now: datetime | None = None,
    rules: list[WatchdogRule] | tuple[WatchdogRule, ...] | None = None,
) -> list[WatchdogAlert]:
    entity = session.get(Entity, entity_id)
    if entity is None:
        return []
    detected_at = now or datetime.utcnow()
    created: list[WatchdogAlert] = []
    demo_flag = is_demo_target(session, entity.id)
    for rule in rules or tuple(_registered_rules):
        candidate = rule(session, entity, detected_at)
        if candidate is None:
            continue
        if _existing_active_alert(session, entity.id, candidate.rule_id) is not None:
            continue
        alert = WatchdogAlert(
            entity_id=entity.id,
            rule_id=candidate.rule_id,
            severity=candidate.severity,
            reason=candidate.reason,
            evidence=candidate.evidence,
            suggested_action=candidate.suggested_action,
            status="open",
            detected_at=detected_at,
            demo_flag=demo_flag,
        )
        session.add(alert)
        created.append(alert)
    if created:
        session.commit()
        for alert in created:
            session.refresh(alert)
    return created


def list_open_alerts(
    session: Session,
    *,
    status: str = "open",
    cluster_id: str | None = None,
    limit: int = 50,
) -> list[WatchdogAlert]:
    if status not in ALERT_STATUSES:
        raise ValueError(f"invalid alert status: {status!r}")
    bounded_limit = max(1, min(limit, 200))
    stmt = select(WatchdogAlert).where(WatchdogAlert.status == status)
    if cluster_id:
        stmt = stmt.join(Entity, Entity.id == WatchdogAlert.entity_id).where(
            Entity.cluster_id == cluster_id
        )
    rows = (
        session.execute(
            stmt.order_by(desc(WatchdogAlert.detected_at), desc(WatchdogAlert.alert_id)).limit(
                bounded_limit
            )
        )
        .scalars()
        .all()
    )
    return sorted(
        rows,
        key=lambda alert: (SEVERITY_RANK.get(alert.severity, 0), alert.detected_at),
        reverse=True,
    )


def acknowledge_alert(session: Session, alert_id: str) -> WatchdogAlert:
    alert = session.get(WatchdogAlert, alert_id)
    if alert is None:
        raise LookupError(alert_id)
    if alert.status == "open":
        alert.status = "acknowledged"
        session.add(alert)
        session.commit()
        session.refresh(alert)
    return alert


def resolve_alert(
    session: Session,
    alert_id: str,
    *,
    resolved_by: str = WATCHDOG_AGENT_NAME,
    resolution_note: str | None = None,
) -> WatchdogAlert:
    alert = session.get(WatchdogAlert, alert_id)
    if alert is None:
        raise LookupError(alert_id)
    alert.status = "resolved"
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = resolved_by
    evidence = dict(alert.evidence or {})
    if resolution_note:
        evidence["resolution_note"] = resolution_note
    alert.evidence = evidence
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


class WatchdogAgent:
    def __init__(
        self,
        *,
        session_factory: SessionFactory | sessionmaker[Session],
        broadcaster: _Broadcaster,
        debounce_sec: float = 2.0,
        sweep_interval_sec: float = 300.0,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._session_factory: SessionFactory = (
            session_factory if not isinstance(session_factory, sessionmaker) else session_factory
        )
        self._sessionmaker = session_factory if isinstance(session_factory, sessionmaker) else None
        self._broadcaster = broadcaster
        self.debounce_sec = debounce_sec
        self.sweep_interval_sec = sweep_interval_sec
        self._sleep = sleeper or asyncio.sleep
        self._tasks: list[asyncio.Task[None]] = []
        self._pending: set[str] = set()
        self._stop = False

    async def detect_entity(self, entity_id: str) -> int:
        try:
            session = self._session_factory()
        except Exception:  # noqa: BLE001
            logger.exception("watchdog: failed to open session")
            return 0
        try:
            alerts = detect_for_entity(session, entity_id)
        except Exception:  # noqa: BLE001
            logger.exception("watchdog: entity detection failed")
            session.rollback()
            return 0
        finally:
            session.close()
        for alert in alerts:
            await self._emit_alert(alert)
        return len(alerts)

    async def sweep_once(self) -> int:
        try:
            session = self._session_factory()
        except Exception:  # noqa: BLE001
            logger.exception("watchdog: failed to open session for sweep")
            return 0
        try:
            ids = list(session.execute(select(Entity.id)).scalars())
        finally:
            session.close()
        total = 0
        for entity_id in ids:
            total += await self.detect_entity(entity_id)
        return total

    async def handle_entity_event(self, entity_id: str) -> None:
        self._pending.add(entity_id)

    async def _debounce_loop(self) -> None:
        while not self._stop:
            await self._sleep(self.debounce_sec)
            pending = sorted(self._pending)
            self._pending.clear()
            for entity_id in pending:
                await self.detect_entity(entity_id)

    async def _sweep_loop(self) -> None:
        while not self._stop:
            await self._sleep(self.sweep_interval_sec)
            try:
                await self.sweep_once()
            except Exception:  # noqa: BLE001
                logger.exception("watchdog: sweep iteration failed")

    async def _event_loop(self) -> None:
        async for envelope in self._broadcaster.subscribe(since=self._broadcaster.current_seq):
            if self._stop:
                break
            if envelope.get("type") in {
                "entity_added",
                "entity_created",
                "entity_updated",
                "entity_modified",
            }:
                entity_id = envelope.get("persisted_id")
                if isinstance(entity_id, str) and entity_id:
                    await self.handle_entity_event(entity_id)

    async def _emit_alert(self, alert: WatchdogAlert) -> None:
        payload = alert_to_dict(alert)
        await self._broadcaster.publish(
            {
                "type": "watchdog_alert_raised",
                "source_id": None,
                "persisted_id": alert.alert_id,
                "timestamp": int(time.time() * 1000),
                "payload": payload,
            }
        )
        await self._broadcaster.publish(
            {
                "type": "insight_flagged",
                "source_id": None,
                "persisted_id": alert.alert_id,
                "timestamp": int(time.time() * 1000),
                "payload": watchdog_insight_from_alert(alert),
            }
        )
        await self._broadcaster.publish(
            {
                "type": "policy_clause_activated",
                "source_id": None,
                "persisted_id": f"watchdog.{alert.rule_id}",
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "policy_id": f"watchdog.{alert.rule_id}",
                    "watchdog_rule_id": alert.rule_id,
                    "alert": payload,
                },
            }
        )
        if self._sessionmaker is None:
            return
        try:
            chain_insert_receipt(
                self._sessionmaker,
                ReceiptInsert(
                    id=f"watchdog_receipt_{alert.alert_id}",
                    action_id=f"watchdog_alert:{alert.alert_id}",
                    agent_name=WATCHDOG_AGENT_NAME,
                    intent="watchdog_alert",
                    target_entity_id=alert.entity_id,
                    cluster_id=(alert.evidence or {}).get("cluster_id"),
                    decision="advise",
                    reason=alert.reason,
                    policy_id=f"watchdog:{alert.rule_id}",
                    passport_id=WATCHDOG_PASSPORT_ID,
                    guidance=alert.suggested_action,
                    suggested_alternative=None,
                    signing_scheme="ed25519",
                    signature="",
                    demo_flag=alert.demo_flag,
                ),
            )
        except Exception:  # noqa: BLE001
            logger.exception("watchdog: receipt insert failed")

    def start(self) -> list[asyncio.Task[None]]:
        if self._tasks:
            return self._tasks
        self._stop = False
        self._tasks = [
            asyncio.create_task(self._event_loop(), name="watchdog.events"),
            asyncio.create_task(self._debounce_loop(), name="watchdog.debounce"),
            asyncio.create_task(self._sweep_loop(), name="watchdog.sweep"),
        ]
        return self._tasks

    async def cancel(self) -> None:
        self._stop = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._tasks = []
