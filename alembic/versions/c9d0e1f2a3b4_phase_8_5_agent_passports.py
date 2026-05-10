"""phase 8.5 agent passports

Revision ID: c9d0e1f2a3b4
Revises: b8e9f0a1b2c3
Create Date: 2026-05-10 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_passports",
        sa.Column("passport_id", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("agent_class", sa.String(), nullable=False),
        sa.Column("owner_email", sa.String(), nullable=False),
        sa.Column("scope_clusters", sqlite.JSON(), nullable=False),
        sa.Column("scope_intents", sqlite.JSON(), nullable=False),
        sa.Column("scope_skills", sqlite.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("not_before", sa.DateTime(), nullable=True),
        sa.Column("kill_switch", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revocation_reason", sa.String(), nullable=True),
        sa.Column("issuer_signature", sa.String(), nullable=False),
        sa.Column("signing_scheme", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("passport_id"),
    )
    op.create_table(
        "passport_credentials",
        sa.Column("credential_hash", sa.String(), nullable=False),
        sa.Column("passport_id", sa.String(), nullable=False),
        sa.Column("presented_count", sa.Integer(), nullable=False),
        sa.Column("last_presented_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["passport_id"], ["agent_passports.passport_id"]),
        sa.PrimaryKeyConstraint("credential_hash"),
    )
    op.create_index(
        op.f("ix_passport_credentials_passport_id"),
        "passport_credentials",
        ["passport_id"],
        unique=False,
    )
    op.add_column("receipts", sa.Column("passport_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_receipts_passport_id"), "receipts", ["passport_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_receipts_passport_id"), table_name="receipts")
    op.drop_column("receipts", "passport_id")
    op.drop_index(op.f("ix_passport_credentials_passport_id"), table_name="passport_credentials")
    op.drop_table("passport_credentials")
    op.drop_table("agent_passports")
