from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from axiom.schema.models import Base
from axiom.storage.db import init_engine, reset_engine


@pytest.fixture(autouse=True)
def default_vault_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_VAULT_KEY", Fernet.generate_key().decode("utf-8"))


@pytest.fixture(autouse=True)
def local_dev_auth_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat the test suite as local-dev (auth opt-out) by default.

    Production auth is now fail-closed (P0-2). The endpoint tests exercise
    handler behavior, not the auth gate, so they run with
    ``AXIOM_AUTH_DISABLED=1`` — the same explicit local-dev escape hatch a
    developer would use. Tests that assert the fail-closed default delete this
    var, and tests that configure ``AXIOM_API_TOKEN`` / ``AXIOM_AUTH_REQUIRED``
    take precedence over it.
    """
    monkeypatch.setenv("AXIOM_AUTH_DISABLED", "1")
    monkeypatch.delenv("AXIOM_ENV", raising=False)


@pytest.fixture()
def db_session(tmp_path: Path) -> Iterator[Session]:
    db_path = tmp_path / "test.db"
    engine = init_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    from axiom.storage.db import get_session

    session = get_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        reset_engine()


@pytest.fixture(autouse=True)
def _reset_policy_cache():
    """Clear the policy lru_cache around every test to prevent cross-test leakage."""
    from axiom.policy import load_policies

    load_policies.cache_clear()
    yield
    load_policies.cache_clear()
