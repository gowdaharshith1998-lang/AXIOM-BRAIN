"""phase 16.18 connectors framework

Revision ID: a2b3c4d5e6f7
Revises: f2a3b4c5d6e7
Create Date: 2026-05-11 00:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connector_configs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("vendor", sa.String(length=32), nullable=False),
        sa.Column("oauth_client_id", sa.String(), nullable=True),
        sa.Column("oauth_client_secret", sa.String(), nullable=True),
        sa.Column("redirect_uri", sa.String(), nullable=True),
        sa.Column("scopes", sqlite.JSON(), nullable=False),
        sa.Column("webhook_secret", sa.String(), nullable=True),
        sa.Column("workspace_id", sa.String(length=128), nullable=True),
        sa.Column("install_state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor"),
    )
    op.create_index("ix_connector_configs_created_at", "connector_configs", ["created_at"])
    op.create_index("ix_connector_configs_updated_at", "connector_configs", ["updated_at"])
    op.create_index("ix_connector_configs_vendor", "connector_configs", ["vendor"])
    op.create_index("ix_connector_configs_workspace_id", "connector_configs", ["workspace_id"])

    op.create_table(
        "connector_states",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("connector_id", sa.String(length=32), nullable=False),
        sa.Column("vendor", sa.String(length=32), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("account_id", sa.String(length=256), nullable=True),
        sa.Column("account_label", sa.String(length=256), nullable=True),
        sa.Column("installed_by", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["connector_id"], ["connector_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connector_states_connector_id", "connector_states", ["connector_id"])
    op.create_index("ix_connector_states_created_at", "connector_states", ["created_at"])
    op.create_index("ix_connector_states_status", "connector_states", ["status"])
    op.create_index("ix_connector_states_updated_at", "connector_states", ["updated_at"])
    op.create_index("ix_connector_states_vendor", "connector_states", ["vendor"])
    op.create_index("ix_connector_states_vendor_status", "connector_states", ["vendor", "status"])

    op.create_table(
        "connector_events",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("vendor", sa.String(length=32), nullable=False),
        sa.Column("connector_state_id", sa.String(length=32), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("payload", sqlite.JSON(), nullable=False),
        sa.Column("signature_ok", sa.Boolean(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("event_timestamp", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["connector_state_id"], ["connector_states.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connector_events_connector_state_id",
        "connector_events",
        ["connector_state_id"],
    )
    op.create_index("ix_connector_events_event_timestamp", "connector_events", ["event_timestamp"])
    op.create_index("ix_connector_events_event_type", "connector_events", ["event_type"])
    op.create_index("ix_connector_events_external", "connector_events", ["vendor", "external_id"])
    op.create_index("ix_connector_events_external_id", "connector_events", ["external_id"])
    op.create_index("ix_connector_events_received_at", "connector_events", ["received_at"])
    op.create_index("ix_connector_events_vendor", "connector_events", ["vendor"])
    op.create_index(
        "ix_connector_events_vendor_received",
        "connector_events",
        ["vendor", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_connector_events_vendor_received", table_name="connector_events")
    op.drop_index("ix_connector_events_vendor", table_name="connector_events")
    op.drop_index("ix_connector_events_received_at", table_name="connector_events")
    op.drop_index("ix_connector_events_external_id", table_name="connector_events")
    op.drop_index("ix_connector_events_external", table_name="connector_events")
    op.drop_index("ix_connector_events_event_type", table_name="connector_events")
    op.drop_index("ix_connector_events_event_timestamp", table_name="connector_events")
    op.drop_index("ix_connector_events_connector_state_id", table_name="connector_events")
    op.drop_table("connector_events")

    op.drop_index("ix_connector_states_vendor_status", table_name="connector_states")
    op.drop_index("ix_connector_states_vendor", table_name="connector_states")
    op.drop_index("ix_connector_states_updated_at", table_name="connector_states")
    op.drop_index("ix_connector_states_status", table_name="connector_states")
    op.drop_index("ix_connector_states_created_at", table_name="connector_states")
    op.drop_index("ix_connector_states_connector_id", table_name="connector_states")
    op.drop_table("connector_states")

    op.drop_index("ix_connector_configs_workspace_id", table_name="connector_configs")
    op.drop_index("ix_connector_configs_vendor", table_name="connector_configs")
    op.drop_index("ix_connector_configs_updated_at", table_name="connector_configs")
    op.drop_index("ix_connector_configs_created_at", table_name="connector_configs")
    op.drop_table("connector_configs")
