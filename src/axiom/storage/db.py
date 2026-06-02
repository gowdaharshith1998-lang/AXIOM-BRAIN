from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final, cast

from sqlalchemy import Index, Table, create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger("axiom.storage.db")

DEFAULT_DATABASE_URL: Final[str] = "sqlite:///./axiom.db"

# P0-5 PRAGMA defaults. Overridable via env so an operator can tune locking
# behaviour without a code change, but the secure/durable defaults win when the
# env var is unset or malformed.
_DEFAULT_BUSY_TIMEOUT_MS: Final[int] = 5000
_DEFAULT_JOURNAL_MODE: Final[str] = "WAL"
_DEFAULT_SYNCHRONOUS: Final[str] = "NORMAL"
_DEFAULT_FOREIGN_KEYS: Final[bool] = True

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:")


def _env_int(name: str, default: int) -> int:
    """Read a non-negative int from env, falling back to ``default`` on any
    missing/malformed value (fail-safe: never crash engine construction)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _sqlite_pragmas() -> dict[str, str | int]:
    """Resolve the per-connection PRAGMA values from env (with safe defaults).

    ``foreign_keys`` and ``synchronous`` only accept the literal pragma tokens
    SQLite understands, so a boolean/string is mapped to ON/OFF here.
    """
    busy_timeout = _env_int("AXIOM_SQLITE_BUSY_TIMEOUT_MS", _DEFAULT_BUSY_TIMEOUT_MS)
    journal_mode = _env_str("AXIOM_SQLITE_JOURNAL_MODE", _DEFAULT_JOURNAL_MODE)
    synchronous = _env_str("AXIOM_SQLITE_SYNCHRONOUS", _DEFAULT_SYNCHRONOUS)
    foreign_keys = _env_bool("AXIOM_SQLITE_FOREIGN_KEYS", _DEFAULT_FOREIGN_KEYS)
    return {
        "journal_mode": journal_mode,
        "busy_timeout": busy_timeout,
        "synchronous": synchronous,
        "foreign_keys": "ON" if foreign_keys else "OFF",
    }


def _register_sqlite_pragmas(engine: Engine) -> None:
    """Attach a ``connect`` listener that applies the AXIOM PRAGMAs on *every*
    new SQLite connection (P0-5).

    Adversarial-review note: a runtime probe reading ``busy_timeout=5000`` from
    Python's sqlite3 default is NOT the same as configuring it — this listener
    sets each pragma explicitly so the value holds regardless of the driver's
    defaults and survives connection pooling/recycling.
    """
    pragmas = _sqlite_pragmas()

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA journal_mode={pragmas['journal_mode']}")
            cursor.execute(f"PRAGMA busy_timeout={pragmas['busy_timeout']}")
            cursor.execute(f"PRAGMA synchronous={pragmas['synchronous']}")
            cursor.execute(f"PRAGMA foreign_keys={pragmas['foreign_keys']}")
        finally:
            cursor.close()


def build_engine(database_url: str | None = None) -> tuple[Engine, sessionmaker[Session]]:
    """Central engine factory — the single source for every AXIOM writer.

    Returns ``(engine, sessionmaker)`` so every ad-hoc engine site (CLI, studio,
    MCP, skill_file_runner) gets the identical configuration:

    - For ``sqlite://`` URLs, a ``connect`` listener applies WAL / busy_timeout
      / synchronous / foreign_keys PRAGMAs (P0-5) on every connection, and
      ``check_same_thread=False`` is set (prerequisite for the connector-sync
      threading work in a parallel workstream).
    - Non-sqlite URLs are passed through unchanged.
    """
    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    connect_args: dict[str, Any] = {}
    if _is_sqlite_url(url):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, future=True, connect_args=connect_args)
    if _is_sqlite_url(url):
        _register_sqlite_pragmas(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return engine, factory


def init_engine(database_url: str | None = None) -> Engine:
    """Initialize global engine + SessionLocal.

    Tests can call this with an in-memory or temp-file URL. Routes through the
    central :func:`build_engine` factory so the global engine carries the same
    SQLite PRAGMAs and thread config as every other writer (P0-5/P1-11).
    """
    global _engine, SessionLocal

    _engine, SessionLocal = build_engine(database_url)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def get_session() -> Session:
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    return SessionLocal()


def create_schema_table(table: Any, engine: Engine) -> None:
    cast(Table, table).create(bind=engine, checkfirst=True)


def schema_table_indexes(table: Any) -> Iterable[Index]:
    return cast(Table, table).indexes


def reset_engine() -> None:
    """Test helper to drop global engine/sessionmaker."""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None


# --- Boot-time migration (P1-11) ---------------------------------------------


def _auto_migrate_enabled() -> bool:
    """Whether boot-time ``alembic upgrade head`` should run (default on)."""
    return os.environ.get("AXIOM_AUTO_MIGRATE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _alembic_config(db_url: str) -> Any:
    """Build an Alembic ``Config`` pointed at the repo ``alembic.ini`` with a
    robustly-resolved ``script_location``.

    The ini lives at the repo root (``src/axiom/storage/db.py`` → up 4). We set
    an absolute ``script_location`` rather than relying on ``%(here)s`` so the
    migration runs correctly regardless of the process CWD.
    """
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[3]
    ini_path = repo_root / "alembic.ini"
    cfg = Config(str(ini_path)) if ini_path.exists() else Config()
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def run_boot_migration(db_url: str, *, engine: Engine | None = None) -> None:
    """Bring the schema to Alembic ``head`` at boot (P1-11), gated by env.

    Behaviour:

    - Disabled when ``AXIOM_AUTO_MIGRATE`` is falsy → no-op.
    - Fresh/empty DB (no ``alembic_version``, no app tables) → ``upgrade head``.
    - DB built by ``Base.metadata.create_all`` (app tables present but no
      ``alembic_version``) → ``stamp head`` so the existing test suite and any
      legacy deployment stay green instead of erroring on duplicate-table
      creation.
    - Already-stamped DB → ``upgrade head`` (applies any pending revisions).

    Failures are logged but not fatal: the ``ensure_*_schema`` helpers in
    ``create_app`` remain the safety net, so a migration hiccup must not take
    the whole server down.
    """
    if not _auto_migrate_enabled():
        log.info("AXIOM_AUTO_MIGRATE disabled; skipping boot-time alembic upgrade")
        return

    from alembic import command

    owns_engine = engine is None
    if engine is None:
        engine, _ = build_engine(db_url)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        has_version = "alembic_version" in table_names
        # "app tables" = anything beyond the alembic bookkeeping table.
        has_app_tables = bool(table_names - {"alembic_version"})
    finally:
        if owns_engine:
            engine.dispose()

    cfg = _alembic_config(db_url)
    try:
        if not has_version and has_app_tables:
            # create_all path: schema exists but is unmanaged. Stamp to head so
            # subsequent upgrades are no-ops and we never re-create tables.
            command.stamp(cfg, "head")
            log.info("stamped existing (unmanaged) schema to alembic head")
        else:
            command.upgrade(cfg, "head")
            log.info("alembic upgrade head complete")
    except Exception:  # noqa: BLE001 - migration must not crash boot
        log.exception("boot-time alembic migration failed; relying on ensure_*_schema fallback")
