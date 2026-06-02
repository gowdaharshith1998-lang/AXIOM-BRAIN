from __future__ import annotations

import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, event, pool
from sqlalchemy.engine import Engine

from axiom.schema.models import Base

# Boot-time migrations can race a concurrent writer (the organizer process, the
# connector sync loop). With sqlite's default busy_timeout of 0 the migration
# would fail immediately with "database is locked". A 30s busy_timeout makes the
# migration wait for the lock instead of aborting the deploy. Applied to every
# sqlite connection the migration engine opens.
_MIGRATION_BUSY_TIMEOUT_MS = 30_000


def _set_sqlite_busy_timeout(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute(f"PRAGMA busy_timeout = {_MIGRATION_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()


# Side-effect imports: every module that defines ORM tables on `Base` must be
# imported here so its tables are registered into `Base.metadata` before
# alembic snapshots `target_metadata`.
import axiom.vault.models  # noqa: E402, F401  -- registers `secrets` table

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
#
# Only configure logging when nothing else has (i.e. alembic is run as a
# standalone CLI). When migrations run programmatically inside the app
# (run_boot_migration) or inside pytest, the host process owns logging —
# re-running fileConfig there would wipe its handlers, and the default
# disable_existing_loggers=True would silently disable every named logger
# (axiom.env, axiom.connectors.sync, ...), breaking both app logs and
# caplog-based tests.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    section = config.get_section(config.config_ini_section, {})
    url = (
        os.environ.get("DATABASE_URL")
        or section.get("sqlalchemy.url")
        or config.get_main_option("sqlalchemy.url")
    )
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    _set_sqlite_busy_timeout(connectable)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
