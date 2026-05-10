"""phase 7c cluster check runs

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-10 03:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cluster_check_runs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("check_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column("last_ingest_at", sa.DateTime(), nullable=True),
        sa.Column("owner", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cluster_check_runs_cluster_id", "cluster_check_runs", ["cluster_id"], unique=False
    )
    op.create_index(
        "ix_cluster_check_runs_cluster_run_at",
        "cluster_check_runs",
        ["cluster_id", "run_at"],
        unique=False,
    )
    op.create_index("ix_cluster_check_runs_run_at", "cluster_check_runs", ["run_at"], unique=False)
    op.create_index(
        "ix_cluster_check_runs_severity", "cluster_check_runs", ["severity"], unique=False
    )
    op.create_index(
        "ix_cluster_check_runs_severity_run_at",
        "cluster_check_runs",
        ["severity", "run_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cluster_check_runs_severity_run_at", table_name="cluster_check_runs")
    op.drop_index("ix_cluster_check_runs_severity", table_name="cluster_check_runs")
    op.drop_index("ix_cluster_check_runs_run_at", table_name="cluster_check_runs")
    op.drop_index("ix_cluster_check_runs_cluster_run_at", table_name="cluster_check_runs")
    op.drop_index("ix_cluster_check_runs_cluster_id", table_name="cluster_check_runs")
    op.drop_table("cluster_check_runs")
