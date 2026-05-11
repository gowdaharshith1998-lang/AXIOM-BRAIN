"""phase 16 durable approval requests

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("action_id", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("passport_id", sa.String(), nullable=True),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("target_entity_id", sa.String(), nullable=True),
        sa.Column("proposed_action", sa.JSON(), nullable=True),
        sa.Column("policy_id", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("guidance", sa.String(), nullable=True),
        sa.Column("required_role", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("resolution_note", sa.String(), nullable=True),
        sa.Column("resume_token", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resume_token"),
    )
    op.create_index("ix_approval_requests_action_id", "approval_requests", ["action_id"])
    op.create_index("ix_approval_requests_agent_name", "approval_requests", ["agent_name"])
    op.create_index("ix_approval_requests_created_at", "approval_requests", ["created_at"])
    op.create_index("ix_approval_requests_expires_at", "approval_requests", ["expires_at"])
    op.create_index("ix_approval_requests_intent", "approval_requests", ["intent"])
    op.create_index("ix_approval_requests_passport_id", "approval_requests", ["passport_id"])
    op.create_index("ix_approval_requests_policy_id", "approval_requests", ["policy_id"])
    op.create_index("ix_approval_requests_resume_token", "approval_requests", ["resume_token"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_index(
        "ix_approval_requests_status_created",
        "approval_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_approval_requests_required_role_status",
        "approval_requests",
        ["required_role", "status"],
    )
    op.create_index(
        "ix_approval_requests_target_entity_id",
        "approval_requests",
        ["target_entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_requests_target_entity_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_required_role_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status_created", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_resume_token", table_name="approval_requests")
    op.drop_index("ix_approval_requests_policy_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_passport_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_intent", table_name="approval_requests")
    op.drop_index("ix_approval_requests_expires_at", table_name="approval_requests")
    op.drop_index("ix_approval_requests_created_at", table_name="approval_requests")
    op.drop_index("ix_approval_requests_agent_name", table_name="approval_requests")
    op.drop_index("ix_approval_requests_action_id", table_name="approval_requests")
    op.drop_table("approval_requests")
