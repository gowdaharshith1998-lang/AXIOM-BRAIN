"""phase 8.6 entity embeddings

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-05-10 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_embeddings",
        sa.Column("entity_id", sa.String(length=32), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("entity_id"),
    )
    op.create_index(
        "ix_entity_embeddings_content_hash",
        "entity_embeddings",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entity_embeddings_content_hash", table_name="entity_embeddings")
    op.drop_table("entity_embeddings")
