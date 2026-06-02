"""connector_events idempotency: nullable external_id + unique constraint

Revision ID: 0004_connector_event_dedup
Revises: b3c4d5e6f7a8
Create Date: 2026-05-30

Adds a UniqueConstraint on (vendor, external_id) so webhook retries that
re-deliver the same event do not create duplicate rows. external_id is made
nullable so events without a stable external id are stored as NULL (SQLite
treats NULLs as distinct in a UNIQUE index, so null-id events never collide).

NOTE: SQLite cannot ALTER an existing table to add a constraint in place, so
this migration uses Alembic's batch mode (table copy). On a fresh test DB the
constraint comes from the SQLAlchemy model via create_all; this migration keeps
Alembic-managed databases in sync.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_connector_event_dedup"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("connector_events", schema=None) as batch_op:
        batch_op.alter_column(
            "external_id",
            existing_type=sa.String(length=512),
            nullable=True,
        )
        batch_op.create_unique_constraint(
            "uq_connector_event_vendor_external",
            ["vendor", "external_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("connector_events", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_connector_event_vendor_external",
            type_="unique",
        )
        batch_op.alter_column(
            "external_id",
            existing_type=sa.String(length=512),
            nullable=False,
        )
