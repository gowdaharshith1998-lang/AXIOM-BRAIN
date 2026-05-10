"""phase 8 skills emitter

Revision ID: b8e9f0a1b2c3
Revises: a7d8e9f0a1b2
Create Date: 2026-05-10 08:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

revision: str = "b8e9f0a1b2c3"
down_revision: str | Sequence[str] | None = "a7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for index_name in (
        "ix_skills_emitted_at",
        "ix_skills_process_entity_id",
        "ix_skills_scope",
        "ix_skills_skill_hash",
        "ix_skills_skill_id",
        "ix_skills_version",
    ):
        op.drop_index(index_name, table_name="skills")
    op.drop_table("skills")
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_config", sqlite.JSON(), nullable=False),
        sa.Column("prompt_template", sa.String(), nullable=False),
        sa.Column("output_schema", sqlite.JSON(), nullable=False),
        sa.Column("llm_provider", sa.String(length=32), nullable=False),
        sa.Column("llm_model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("total_runs", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skills_created_at"), "skills", ["created_at"], unique=False)
    op.create_index(op.f("ix_skills_intent"), "skills", ["intent"], unique=False)
    op.create_index(op.f("ix_skills_llm_provider"), "skills", ["llm_provider"], unique=False)
    op.create_index(op.f("ix_skills_name"), "skills", ["name"], unique=False)
    op.create_index("ix_skills_status_intent", "skills", ["status", "intent"], unique=False)
    op.create_index(op.f("ix_skills_status"), "skills", ["status"], unique=False)
    op.create_index(op.f("ix_skills_updated_at"), "skills", ["updated_at"], unique=False)
    op.create_table(
        "skill_runs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("skill_id", sa.String(length=32), nullable=False),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_payload", sqlite.JSON(), nullable=False),
        sa.Column("output_payload", sqlite.JSON(), nullable=True),
        sa.Column("receipt_id", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skill_runs_agent_name"), "skill_runs", ["agent_name"], unique=False)
    op.create_index(op.f("ix_skill_runs_receipt_id"), "skill_runs", ["receipt_id"], unique=False)
    op.create_index(op.f("ix_skill_runs_run_at"), "skill_runs", ["run_at"], unique=False)
    op.create_index("ix_skill_runs_skill_run_at", "skill_runs", ["skill_id", "run_at"], unique=False)
    op.create_index(op.f("ix_skill_runs_skill_id"), "skill_runs", ["skill_id"], unique=False)
    op.create_index(op.f("ix_skill_runs_status"), "skill_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_skill_runs_status"), table_name="skill_runs")
    op.drop_index(op.f("ix_skill_runs_skill_id"), table_name="skill_runs")
    op.drop_index("ix_skill_runs_skill_run_at", table_name="skill_runs")
    op.drop_index(op.f("ix_skill_runs_run_at"), table_name="skill_runs")
    op.drop_index(op.f("ix_skill_runs_receipt_id"), table_name="skill_runs")
    op.drop_index(op.f("ix_skill_runs_agent_name"), table_name="skill_runs")
    op.drop_table("skill_runs")
    op.drop_index(op.f("ix_skills_updated_at"), table_name="skills")
    op.drop_index(op.f("ix_skills_status"), table_name="skills")
    op.drop_index("ix_skills_status_intent", table_name="skills")
    op.drop_index(op.f("ix_skills_name"), table_name="skills")
    op.drop_index(op.f("ix_skills_llm_provider"), table_name="skills")
    op.drop_index(op.f("ix_skills_intent"), table_name="skills")
    op.drop_index(op.f("ix_skills_created_at"), table_name="skills")
    op.drop_table("skills")
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("skill_id", sa.String(length=256), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("skill_hash", sa.String(length=128), nullable=False),
        sa.Column("process_entity_id", sa.String(length=32), nullable=False),
        sa.Column("emitted_at", sa.DateTime(), nullable=False),
        sa.Column("signed_metadata", sqlite.JSON(), nullable=False),
        sa.Column("markdown", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["process_entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skills_emitted_at", "skills", ["emitted_at"], unique=False)
    op.create_index("ix_skills_process_entity_id", "skills", ["process_entity_id"], unique=False)
    op.create_index("ix_skills_scope", "skills", ["scope"], unique=False)
    op.create_index("ix_skills_skill_hash", "skills", ["skill_hash"], unique=False)
    op.create_index("ix_skills_skill_id", "skills", ["skill_id"], unique=False)
    op.create_index("ix_skills_version", "skills", ["version"], unique=False)
