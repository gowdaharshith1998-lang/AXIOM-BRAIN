from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from sqlalchemy import Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from axiom.schema.models import ConnectorConfigRow, ConnectorEventRow, ConnectorStateRow
from axiom.storage.db import get_session

ConnectorFactory = Callable[[], Any]


class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ConnectorFactory] = {}

    def register_connector(self, vendor: str, factory: ConnectorFactory) -> None:
        self._factories[vendor] = factory

    def get_connector(self, vendor: str) -> Any:
        try:
            return self._factories[vendor]()
        except KeyError as exc:
            raise KeyError(f"connector not registered: {vendor}") from exc


registry = ConnectorRegistry()


def register_connector(vendor: str, factory: ConnectorFactory) -> None:
    registry.register_connector(vendor, factory)


def get_connector(vendor: str) -> Any:
    return registry.get_connector(vendor)


def list_installed(session_factory: Callable[[], Session] | None = None) -> list[dict[str, Any]]:
    factory = session_factory or get_session
    with factory() as session:
        rows = session.execute(
            select(ConnectorStateRow).order_by(ConnectorStateRow.vendor, ConnectorStateRow.id)
        ).scalars().all()
        return [
            {
                "id": row.id,
                "connector_id": row.connector_id,
                "vendor": row.vendor,
                "account_id": row.account_id,
                "account_label": row.account_label,
                "installed_by": row.installed_by,
                "status": row.status,
                "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            }
            for row in rows
        ]


def ensure_connectors_schema(engine: Engine) -> None:
    tables = (
        cast(Table, ConnectorConfigRow.__table__),
        cast(Table, ConnectorStateRow.__table__),
        cast(Table, ConnectorEventRow.__table__),
    )
    for table in tables:
        table.create(bind=engine, checkfirst=True)
    for table in tables:
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def _placeholder_factory() -> Any:
    return None


for _vendor in ("github", "linear", "slack", "notion", "gmail"):
    register_connector(_vendor, _placeholder_factory)
