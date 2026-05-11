from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from axiom.schema.models import WatchdogAlert

PredicateFunc = Callable[..., Any]

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")

_RATE_HISTORY: dict[tuple[str, str, str | None], list[datetime]] = defaultdict(list)


def contains_pii(value: Any) -> bool:
    text = _stringify(value)
    if EMAIL_RE.search(text) or SSN_RE.search(text) or PHONE_RE.search(text):
        return True
    for match in CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if len(digits) >= 13 and _luhn_valid(digits):
            return True
    return False


def contains_pii_predicate(
    _action: Any,
    _passport: Any,
    _entity: Any,
    _session: Session | None,
    value: Any,
) -> bool:
    return contains_pii(value)


def now_predicate(_action: Any, _passport: Any, _entity: Any, _session: Session | None) -> datetime:
    return datetime.utcnow()


def days_predicate(
    _action: Any,
    _passport: Any,
    _entity: Any,
    _session: Session | None,
    count: int,
) -> timedelta:
    return timedelta(days=count)


def watchdog_has_open_alert_on(
    _action: Any,
    _passport: Any,
    entity: Any,
    session: Session | None,
    target: Any = None,
    *,
    rule_id: str | None = None,
    severity: str | None = None,
) -> bool:
    return watchdog_alert_count(
        _action,
        _passport,
        entity,
        session,
        target,
        rule_id=rule_id,
        severity=severity,
    ) > 0


def watchdog_alert_count(
    _action: Any,
    _passport: Any,
    entity: Any,
    session: Session | None,
    target: Any = None,
    *,
    rule_id: str | None = None,
    severity: str | None = None,
) -> int:
    if session is None:
        return 0
    target_entity = target if target is not None else entity
    entity_id = getattr(target_entity, "id", None)
    if entity_id is None:
        return 0
    stmt = select(WatchdogAlert).where(
        WatchdogAlert.entity_id == entity_id,
        WatchdogAlert.status.in_(["open", "acknowledged"]),
    )
    if rule_id is not None:
        stmt = stmt.where(WatchdogAlert.rule_id == rule_id)
    if severity is not None:
        stmt = stmt.where(WatchdogAlert.severity == severity)
    return len(session.execute(stmt).scalars().all())


def rate_same_action_within(
    action: Any,
    _passport: Any,
    _entity: Any,
    _session: Session | None,
    *,
    seconds: int,
) -> bool:
    timestamp = getattr(action, "timestamp", None) or datetime.utcnow()
    key = (
        str(getattr(action, "agent_name", "")),
        str(getattr(action, "intent", "")),
        getattr(action, "target_entity_id", None),
    )
    cutoff = timestamp - timedelta(seconds=seconds)
    recent = [seen for seen in _RATE_HISTORY[key] if seen >= cutoff]
    matched = bool(recent)
    recent.append(timestamp)
    _RATE_HISTORY[key] = recent
    return matched


def reset_rate_history() -> None:
    _RATE_HISTORY.clear()


def time_off_hours_utc(
    action: Any,
    _passport: Any,
    _entity: Any,
    _session: Session | None,
    *,
    start_hour: int,
    end_hour: int,
) -> bool:
    timestamp = getattr(action, "timestamp", None) or datetime.utcnow()
    hour = int(timestamp.hour)
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def connector_vendor(
    _action: Any,
    _passport: Any,
    entity: Any,
    _session: Session | None,
    target: Any = None,
) -> str:
    target_entity = target if target is not None else entity
    source_id = str(getattr(target_entity, "source_id", "") or "")
    vendor = source_id.split(":", 1)[0] if ":" in source_id else ""
    if vendor in {"gmail", "slack", "notion", "linear", "github", "synthetic"}:
        return vendor
    data = getattr(target_entity, "data", None)
    if isinstance(data, dict) and isinstance(data.get("vendor"), str):
        return str(data["vendor"])
    return "synthetic"


def connector_is_external(
    _action: Any,
    _passport: Any,
    entity: Any,
    _session: Session | None,
    target: Any = None,
) -> bool:
    target_entity = target if target is not None else entity
    data = getattr(target_entity, "data", None)
    if not isinstance(data, dict):
        return False
    if data.get("external") is True:
        return True
    vendor = connector_vendor(_action, _passport, target_entity, _session)
    if vendor == "gmail":
        sender = str(data.get("from") or data.get("sender") or "")
        workspace_domain = str(data.get("workspace_domain") or "")
        if not sender or not workspace_domain or "@" not in sender:
            return False
        return sender.rsplit("@", 1)[1].lower() != workspace_domain.lower()
    if vendor == "slack":
        return data.get("is_im") is True and data.get("is_member") is False
    return False


def connector_sensitive_label(
    _action: Any,
    _passport: Any,
    entity: Any,
    _session: Session | None,
    target: Any = None,
) -> bool:
    target_entity = target if target is not None else entity
    data = getattr(target_entity, "data", None)
    if not isinstance(data, dict):
        return False
    raw_labels = data.get("labels") or data.get("labelIds") or data.get("label_ids") or []
    if isinstance(raw_labels, str):
        labels = [raw_labels]
    else:
        labels = [str(label) for label in raw_labels]
    sensitive = {"confidential", "legal", "executive"}
    return any(label.lower() in sensitive for label in labels)


PREDICATES: dict[str, PredicateFunc] = {
    "contains_pii": contains_pii_predicate,
    "now": now_predicate,
    "days": days_predicate,
    "watchdog.has_open_alert_on": watchdog_has_open_alert_on,
    "watchdog.alert_count": watchdog_alert_count,
    "rate.same_action_within": rate_same_action_within,
    "time.off_hours_utc": time_off_hours_utc,
    "connector.is_external": connector_is_external,
    "connector.vendor": connector_vendor,
    "connector.sensitive_label": connector_sensitive_label,
}


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return str(value)


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0
