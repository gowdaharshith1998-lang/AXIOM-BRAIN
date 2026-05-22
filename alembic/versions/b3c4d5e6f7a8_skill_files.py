"""skill_files + skill_file_versions

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_files",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("yaml_text", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_skill_files_name", "skill_files", ["name"], unique=True)

    op.create_table(
        "skill_file_versions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "skill_file_id",
            sa.String(length=32),
            sa.ForeignKey("skill_files.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("yaml_text", sa.Text(), nullable=False),
        sa.Column("saved_at", sa.String(), nullable=False),
        sa.Column("saved_by", sa.String(length=128), nullable=True),
        sa.Column("validation_status", sa.String(length=16), nullable=False),
        sa.Column("validation_errors", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_skill_file_versions_skill_file_id",
        "skill_file_versions",
        ["skill_file_id"],
    )
    op.create_index(
        "ix_skill_file_versions_unique",
        "skill_file_versions",
        ["skill_file_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_skill_file_versions_unique", table_name="skill_file_versions")
    op.drop_index("ix_skill_file_versions_skill_file_id", table_name="skill_file_versions")
    op.drop_table("skill_file_versions")
    op.drop_index("ix_skill_files_name", table_name="skill_files")
    op.drop_table("skill_files")
