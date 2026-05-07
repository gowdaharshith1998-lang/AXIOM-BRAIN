from __future__ import annotations

import argparse
import asyncio
import logging

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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

