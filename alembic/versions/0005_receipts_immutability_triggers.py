"""receipts append-only immutability triggers (SQLite)

Revision ID: 0005_receipts_immutability
Revises: 0004_connector_event_dedup
Create Date: 2026-06-01

P1-3 (GOV-SIG-004 / GOV-CHAIN-005): the signed receipt chain is only
tamper-evident if rows cannot be silently rewritten or removed by a DB writer.
This migration adds SQLite triggers that ABORT any UPDATE or DELETE against the
``receipts`` table, enforcing append-only semantics at the storage layer.

The triggers are guarded on the dialect being ``sqlite`` so a future Postgres
migration path is not broken (Postgres would use a row-level BEFORE trigger
calling a PL/pgSQL function with RAISE EXCEPTION, added in a separate revision).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_receipts_immutability"
down_revision: str | None = "0004_connector_event_dedup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        # Triggers below are SQLite-specific. Other dialects (e.g. Postgres) get
        # their own immutability enforcement in a dialect-specific migration.
        return
    op.execute(
        "CREATE TRIGGER receipts_no_update BEFORE UPDATE ON receipts "
        "BEGIN SELECT RAISE(ABORT, 'receipts are append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER receipts_no_delete BEFORE DELETE ON receipts "
        "BEGIN SELECT RAISE(ABORT, 'receipts are append-only'); END"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute("DROP TRIGGER IF EXISTS receipts_no_delete")
    op.execute("DROP TRIGGER IF EXISTS receipts_no_update")
