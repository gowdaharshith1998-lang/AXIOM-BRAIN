"""phase 5.8 watchdog alerts

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-05-10 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchdog_alerts",
        sa.Column("alert_id", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=32), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("suggested_action", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("demo_flag", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    op.create_index("ix_watchdog_alerts_entity_id", "watchdog_alerts", ["entity_id"], unique=False)
    op.create_index("ix_watchdog_alerts_rule_id", "watchdog_alerts", ["rule_id"], unique=False)
    op.create_index("ix_watchdog_alerts_severity", "watchdog_alerts", ["severity"], unique=False)
    op.create_index("ix_watchdog_alerts_status", "watchdog_alerts", ["status"], unique=False)
    op.create_index(
        "ix_watchdog_alerts_status_detected",
        "watchdog_alerts",
        ["status", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_watchdog_alerts_entity_rule_status",
        "watchdog_alerts",
        ["entity_id", "rule_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_watchdog_alerts_entity_rule_status", table_name="watchdog_alerts")
    op.drop_index("ix_watchdog_alerts_status_detected", table_name="watchdog_alerts")
    op.drop_index("ix_watchdog_alerts_status", table_name="watchdog_alerts")
    op.drop_index("ix_watchdog_alerts_severity", table_name="watchdog_alerts")
    op.drop_index("ix_watchdog_alerts_rule_id", table_name="watchdog_alerts")
    op.drop_index("ix_watchdog_alerts_entity_id", table_name="watchdog_alerts")
    op.drop_table("watchdog_alerts")
