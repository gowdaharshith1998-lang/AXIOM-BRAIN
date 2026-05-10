"""phase 7d llm provider keys

Revision ID: a7d8e9f0a1b2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-10 07:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d8e9f0a1b2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_keys",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("encrypted_key", sa.String(length=8192), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=4), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_test_status", sa.String(length=16), nullable=False, server_default="untested"),
        sa.Column("demo_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("llm_provider_keys")
