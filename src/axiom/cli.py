from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.ingest.pipeline import IngestPipeline
from axiom.sources.synthetic import SyntheticSource


def cmd_ingest(args: argparse.Namespace) -> None:
    engine = create_engine(args.db_url, future=True)
    session_local = sessionmaker(bind=engine, future=True)
    broadcaster = EventBroadcaster()

    if args.source != "synthetic":
        raise SystemExit(f"unknown source: {args.source}")

    source = SyntheticSource()

    async def run() -> None:
        with session_local() as session:
            pipeline = IngestPipeline(source=source, session=session, broadcaster=broadcaster)
            count = await pipeline.run(since=None)
            session.commit()
            print(f"ingested {count} events from {args.source}")

    asyncio.run(run())


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from axiom.studio.server import create_app

    app = create_app(
        db_url=args.db_url,
        live=args.live,
        live_rate=args.rate,
        live_pause_after=args.pause_after,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def cmd_vault_init(args: argparse.Namespace) -> None:
    """Generate a fresh Fernet master key and print copy/paste instructions.

    Refuses to overwrite if ``AXIOM_VAULT_KEY`` is already set in the current
    environment — rotation is destructive (existing ciphertext becomes
    unreadable) and must be a deliberate manual step.
    """
    from axiom.vault import generate_master_key
    from axiom.vault.crypto import ENV_VAR

    if os.environ.get(ENV_VAR):
        print(
            f"refusing to generate a new key: {ENV_VAR} is already set in the "
            f"current environment.\n"
            f"rotating the master key invalidates every existing encrypted secret. "
            f"if you really want to rotate, unset {ENV_VAR} first, generate, then "
            f"manually re-store every secret with the new key.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    key = generate_master_key()
    print(f"# AXIOM vault master key (Fernet, 32-byte url-safe base64)")
    print(f"# Add the line below to your .env file. Keep it secret. Back it up.")
    print(f"# Losing it makes every stored secret permanently unreadable.")
    print(f"{ENV_VAR}={key}")


def cmd_mcp_serve(args: argparse.Namespace) -> None:
    from axiom.mcp.server import serve_stdio

    serve_stdio(db_url=args.db_url, api_base_url=args.api_base_url)


def cmd_vault_status(args: argparse.Namespace) -> None:
    """Report whether the vault is unlocked and per-provider secret counts.

    Never prints plaintext, ciphertext, or key material.
    """
    from axiom.vault import list_secrets
    from axiom.vault.crypto import ENV_VAR

    from axiom.storage.db import init_engine

    init_engine(args.db_url)

    locked = not os.environ.get(ENV_VAR)
    if locked:
        print(f"vault: LOCKED ({ENV_VAR} not set)")
    else:
        print("vault: unlocked")

    metas = list_secrets()
    print(f"stored secrets: {len(metas)}")
    if metas:
        counts = Counter(m.provider_id for m in metas)
        for provider in sorted(counts):
            print(f"  {provider}: {counts[provider]}")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="axiom")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="ingest from a source into local db")
    p_ingest.add_argument("--source", default="synthetic")
    p_ingest.add_argument("--db-url", default="sqlite:///./axiom.db")
    p_ingest.set_defaults(func=cmd_ingest)

    p_serve = sub.add_parser("serve", help="run the studio API + WebSocket server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--db-url", default="sqlite:///./axiom.db")
    p_serve.add_argument("--live", action="store_true")
    p_serve.add_argument("--rate", type=float, default=0.125)
    p_serve.add_argument("--pause-after", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    p_mcp = sub.add_parser("mcp-serve", help="run AXIOM MCP server over stdio")
    p_mcp.add_argument("--db-url", default="sqlite:///./axiom.db")
    p_mcp.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    p_mcp.set_defaults(func=cmd_mcp_serve)

    p_vault = sub.add_parser("vault", help="manage the encrypted secrets vault")
    vault_sub = p_vault.add_subparsers(dest="vault_cmd", required=True)

    p_vault_init = vault_sub.add_parser(
        "init", help="generate a fresh Fernet master key and print it to stdout"
    )
    p_vault_init.set_defaults(func=cmd_vault_init)

    p_vault_status = vault_sub.add_parser(
        "status", help="report vault lock state and per-provider secret counts"
    )
    p_vault_status.add_argument("--db-url", default="sqlite:///./axiom.db")
    p_vault_status.set_defaults(func=cmd_vault_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

