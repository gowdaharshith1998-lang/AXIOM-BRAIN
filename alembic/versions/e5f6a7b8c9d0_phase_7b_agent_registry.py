"""phase 7b agent registry

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-10 02:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_registry",
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("total_actions", sa.Integer(), nullable=False),
        sa.Column("allow_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("deny_count", sa.Integer(), nullable=False),
        sa.Column("last_intent", sa.String(), nullable=True),
        sa.Column("last_action_id", sa.String(), nullable=True),
        sa.Column("agent_type", sa.String(length=32), nullable=False),
        sa.Column("demo_flag", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("agent_name"),
    )
    op.create_index("ix_agent_registry_agent_type", "agent_registry", ["agent_type"], unique=False)
    op.create_index("ix_agent_registry_first_seen", "agent_registry", ["first_seen"], unique=False)
    op.create_index("ix_agent_registry_last_seen", "agent_registry", ["last_seen"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_registry_last_seen", table_name="agent_registry")
    op.drop_index("ix_agent_registry_first_seen", table_name="agent_registry")
    op.drop_index("ix_agent_registry_agent_type", table_name="agent_registry")
    op.drop_table("agent_registry")
