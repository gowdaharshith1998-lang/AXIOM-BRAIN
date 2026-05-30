#!/usr/bin/env python
"""Seed the brain with the synthetic demo fixture (offline, no network).

Phase 2 (engineering-audit §4): the committed DB is empty/ephemeral, so the
repo needs a reproducible way to get a populated brain for local/dev work
WITHOUT committing a binary DB. This drives the canonical SyntheticSource
through the real IngestPipeline (the same path as ``axiom ingest --source
synthetic``), so the synthetic company fixture is loaded exactly the way real
ingest would load it.

Every entity ingested this way has ``source_id = "synthetic-default"``, which
``axiom.govern.demo_flag.is_demo_target`` treats as demo data — so it can never
be mistaken for real ingested data (governance receipts and the /api/health
``policy_mode`` surface the demo flag).

For a REAL ingest pass over configured connectors, use scripts/seed_real.py.

Usage:
    python scripts/seed_demo.py [--db-url sqlite:///./axiom.db]

Idempotent: re-running upserts the same entities/edges (the pipeline keys on
stable ids derived from the fixture nicks).
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.ingest.broadcaster import EventBroadcaster
from axiom.ingest.pipeline import IngestPipeline
from axiom.schema.models import Base
from axiom.sources.synthetic import SyntheticSource


def seed_demo(db_url: str) -> int:
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    broadcaster = EventBroadcaster()
    source = SyntheticSource()

    async def _run() -> int:
        with session_local() as session:
            pipeline = IngestPipeline(source=source, session=session, broadcaster=broadcaster)
            count = await pipeline.run(since=None)
            session.commit()
            return int(count)

    return asyncio.run(_run())


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo (synthetic) brain.")
    parser.add_argument("--db-url", default="sqlite:///./axiom.db")
    args = parser.parse_args()

    count = seed_demo(args.db_url)
    print(
        f"[seed_demo] DEMO data loaded into {args.db_url}: {count} ingest events "
        f"(entities + edges), all under source_id='synthetic-default' (demo-flagged)."
    )
    print(
        "[seed_demo] This is synthetic demo data, not real ingest. "
        "Run scripts/seed_real.py for a real connector sync."
    )


if __name__ == "__main__":
    main()
