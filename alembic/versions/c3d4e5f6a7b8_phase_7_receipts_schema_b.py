"""phase 7 receipts schema b

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-10 00:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_receipts_receipt_type"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_merkle_leaf_index"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_created_at"), table_name="receipts")
    op.drop_table("receipts")
    op.create_table(
        "receipts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("action_id", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("target_entity_id", sa.String(), nullable=True),
        sa.Column("cluster_id", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("policy_id", sa.String(), nullable=False),
        sa.Column("guidance", sa.String(), nullable=True),
        sa.Column("suggested_alternative", sa.String(), nullable=True),
        sa.Column("signing_scheme", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("prev_hash", sa.String(), nullable=True),
        sa.Column("this_hash", sa.String(), nullable=False),
        sa.Column("calibra_state", sa.String(), nullable=True),
        sa.Column("demo_flag", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id", name="uq_receipts_action_id"),
    )
    op.create_index("ix_receipts_action_id", "receipts", ["action_id"], unique=False)
    op.create_index("ix_receipts_agent_name", "receipts", ["agent_name"], unique=False)
    op.create_index("ix_receipts_created_at", "receipts", ["created_at"], unique=False)
    op.create_index("ix_receipts_created_at_desc", "receipts", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_receipts_created_at_desc", table_name="receipts")
    op.drop_index("ix_receipts_created_at", table_name="receipts")
    op.drop_index("ix_receipts_agent_name", table_name="receipts")
    op.drop_index("ix_receipts_action_id", table_name="receipts")
    op.drop_table("receipts")
    op.create_table(
        "receipts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("receipt_type", sa.String(length=64), nullable=False),
        sa.Column("merkle_leaf_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("signature_ed25519_b64", sa.String(length=8192), nullable=True),
        sa.Column("signature_mldsa_b64", sa.String(length=8192), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receipts_created_at"), "receipts", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_receipts_merkle_leaf_index"),
        "receipts",
        ["merkle_leaf_index"],
        unique=False,
    )
    op.create_index(op.f("ix_receipts_receipt_type"), "receipts", ["receipt_type"], unique=False)
