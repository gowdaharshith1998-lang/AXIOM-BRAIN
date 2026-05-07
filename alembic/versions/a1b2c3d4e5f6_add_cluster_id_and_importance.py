"""add cluster_id and composite_importance to entities

Revision ID: a1b2c3d4e5f6
Revises: 309b33ebec31
Create Date: 2026-05-07 00:40:00.000000

Phase 5.7 — self-organizing brain. Adds two columns:
  * cluster_id: nullable semantic cluster label (one of seven canonical
    cluster ids, see axiom.organize.clusters.SEMANTIC_CLUSTERS).
  * composite_importance: PageRank + degree + recency blended score
    in [0.0, 1.0]. Recomputed periodically by the background scorer.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "309b33ebec31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("cluster_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column(
            "composite_importance",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )
    op.create_index(
        "ix_entities_cluster_id", "entities", ["cluster_id"], unique=False
    )
    op.create_index(
        "ix_entities_composite_importance",
        "entities",
        ["composite_importance"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entities_composite_importance", table_name="entities")
    op.drop_index("ix_entities_cluster_id", table_name="entities")
    op.drop_column("entities", "composite_importance")
    op.drop_column("entities", "cluster_id")
