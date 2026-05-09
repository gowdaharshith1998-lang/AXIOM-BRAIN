"""add secrets table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09 12:00:00.000000

Phase 5.13.0 — vault foundation. Adds the encrypted-credentials table that
unblocks every later feature touching API keys / OAuth tokens.

Schema:
  * id              — UUIDv7 primary key (32 hex chars)
  * provider_id     — free-text logical identifier ("anthropic", "openai", ...)
  * key_name        — human label, defaults to provider_id at the API layer
  * encrypted_value — Fernet token (AES-128-CBC + HMAC-SHA256), base64 string
  * status          — "untested" | "valid" | "invalid" | "expired"
  * last_tested_at  — nullable timestamp of most recent verification
  * created_at, updated_at — bookkeeping
  * unique(provider_id, key_name) — no duplicate identities
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("key_name", sa.String(length=128), nullable=False),
        sa.Column("encrypted_value", sa.String(length=8192), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="untested"),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "key_name", name="uq_secrets_provider_key"),
    )
    op.create_index(op.f("ix_secrets_provider_id"), "secrets", ["provider_id"], unique=False)
    op.create_index(op.f("ix_secrets_status"), "secrets", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_secrets_status"), table_name="secrets")
    op.drop_index(op.f("ix_secrets_provider_id"), table_name="secrets")
    op.drop_table("secrets")
