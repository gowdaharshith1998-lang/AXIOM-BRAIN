from __future__ import annotations

import sys
from typing import Any

from axiom import cli


def test_mcp_serve_subcommand_dispatches(monkeypatch: Any) -> None:
    captured: dict[str, str] = {}

    def fake_serve_stdio(*, db_url: str, api_base_url: str) -> None:
        captured["db_url"] = db_url
        captured["api_base_url"] = api_base_url

    import axiom.mcp.server as mcp_server

    monkeypatch.setattr(mcp_server, "serve_stdio", fake_serve_stdio)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "axiom",
            "mcp-serve",
            "--db-url",
            "sqlite:///./custom.db",
            "--api-base-url",
            "http://127.0.0.1:8123",
        ],
    )

    cli.main()

    assert captured["db_url"] == "sqlite:///./custom.db"
    assert captured["api_base_url"] == "http://127.0.0.1:8123"
