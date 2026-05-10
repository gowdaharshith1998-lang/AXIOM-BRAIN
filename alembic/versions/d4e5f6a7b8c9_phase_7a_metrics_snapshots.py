"""phase 7a metrics snapshots

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-10 01:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metrics_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("receipt_count", sa.Integer(), nullable=False),
        sa.Column("allow_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("deny_count", sa.Integer(), nullable=False),
        sa.Column("agent_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date", name="uq_metrics_snapshots_snapshot_date"),
    )
    op.execute(
        "CREATE INDEX ix_metrics_snapshots_snapshot_date_desc "
        "ON metrics_snapshots (snapshot_date DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_metrics_snapshots_snapshot_date_desc", table_name="metrics_snapshots")
    op.drop_table("metrics_snapshots")
