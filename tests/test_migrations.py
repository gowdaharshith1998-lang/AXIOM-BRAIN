from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def test_alembic_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    repo_root = Path(__file__).parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))

    db_path = tmp_path / "alembic_test.db"
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

