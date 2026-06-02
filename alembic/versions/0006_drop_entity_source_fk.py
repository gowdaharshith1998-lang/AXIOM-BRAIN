"""drop entities.source_id -> sources.id foreign key

Revision ID: 0006_drop_entity_source_fk
Revises: 0005_receipts_immutability
Create Date: 2026-06-01

P0-5 follow-up: enabling ``PRAGMA foreign_keys=ON`` for every SQLite connection
exposed a pre-existing data-model inconsistency. ``entities.source_id`` is an
OVERLOADED column:

* Synthetic ingest paths store a real ``sources.id`` ('synthetic-default',
  'live-synthetic').
* Connector ingest paths store an external 'vendor:type:id' reference
  ('github:issue:12', 'linear:issue:issue_1') that doubles as the per-entity
  upsert dedup key (IngestPipeline._persist_entity, upsert_by_source_id) and is
  NOT a row in the ``sources`` table.

With FK enforcement on, the connector reference values violated the
``entities.source_id -> sources.id`` constraint, breaking every connector
ingest. The column is intentionally NOT a foreign key; this migration drops the
constraint to match the (now honest) ORM model. All legitimate FKs are kept.

SQLite cannot ALTER an existing table to drop a constraint in place, so this
uses Alembic's batch mode (table copy). The original FK is unnamed, so a
``copy_from`` Table definition is supplied describing the DESIRED shape (no FK,
all eight columns, all seven indexes). ``recreate="always"`` forces batch mode
to rebuild ``entities`` from that definition, copy the data, and recreate the
indexes. Because the supplied definition omits the foreign key, the rebuilt
table no longer carries it. ``source_id`` is also widened to String(255) here so
the persisted column matches the (length-honest) ORM model.

Reversible: ``downgrade`` rebuilds the table and re-adds the FK constraint.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

revision: str = "0006_drop_entity_source_fk"
down_revision: str | None = "0005_receipts_immutability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entities_table(*, with_fk: bool) -> sa.Table:
    """Reflect-free definition of ``entities`` at this revision.

    Mirrors the cumulative shape produced by the initial schema plus
    ``a1b2c3d4e5f6_add_cluster_id_and_importance``: eight columns and seven
    indexes. ``with_fk`` toggles the overloaded ``source_id -> sources.id``
    foreign key that this migration removes (and ``downgrade`` restores). The
    indexes MUST be declared here so batch-mode table recreation rebuilds every
    one of them (a later migration's downgrade drops two of them by name).
    """
    metadata = sa.MetaData()
    args: list[sa.Column[object] | sa.schema.SchemaItem] = [
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("data", sqlite.JSON(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=True),
        sa.Column(
            "composite_importance",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.PrimaryKeyConstraint("id"),
    ]
    if with_fk:
        args.append(sa.ForeignKeyConstraint(["source_id"], ["sources.id"]))
    table = sa.Table("entities", metadata, *args)
    # Declare all indexes so batch recreation preserves them.
    sa.Index("ix_entities_created_at", table.c.created_at)
    sa.Index("ix_entities_source_id", table.c.source_id)
    sa.Index("ix_entities_type", table.c.type)
    sa.Index("ix_entities_type_created", table.c.type, table.c.created_at)
    sa.Index("ix_entities_updated_at", table.c.updated_at)
    sa.Index("ix_entities_cluster_id", table.c.cluster_id)
    sa.Index("ix_entities_composite_importance", table.c.composite_importance)
    return table


def upgrade() -> None:
    # copy_from describes the DESIRED shape (no FK). recreate="always" rebuilds
    # entities from it, dropping the unnamed sources FK while preserving data and
    # every index.
    with op.batch_alter_table(
        "entities",
        copy_from=_entities_table(with_fk=False),
        recreate="always",
    ):
        pass


def downgrade() -> None:
    with op.batch_alter_table(
        "entities",
        copy_from=_entities_table(with_fk=False),
        recreate="always",
    ) as batch_op:
        batch_op.create_foreign_key(
            "fk_entities_source_id_sources",
            "sources",
            ["source_id"],
            ["id"],
        )
