#!/usr/bin/env python
"""Run a REAL ingest pass over configured connectors and report counts.

Phase 2 (engineering-audit §4): the reproducible "real data" artifact is this
script plus the connector configs in the DB (vault-encrypted secrets) — NOT a
binary DB committed to git. Given connectors that have been configured and
authorized (GitHub, Linear, Slack, Notion, Gmail), this triggers one sync cycle
across every connected connector via the same code path the background sync
runner uses (``sync_all_connected_connectors``), then prints the per-vendor
ingest summary.

Requirements (this is real, networked work — "wired, unproven" without them):
  - AXIOM_VAULT_KEY set (vault unlocked) so connector secrets can be decrypted.
  - At least one connector configured + authorized (Settings -> Integrations, or
    POST /api/internal/connectors/...). Gmail in particular requires the
    granular OAuth re-consent described in the README "Seeding" section.

Usage:
    python scripts/seed_real.py [--db-url sqlite:///./axiom.db]

Exit codes: 0 on completion (even if an individual connector reports an error in
its summary entry); 2 if the vault is locked (nothing could be synced).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from axiom.connectors.sync_runner import sync_all_connected_connectors
from axiom.env import load_axiom_env
from axiom.ingest.broadcaster import EventBroadcaster
from axiom.schema.models import Base
from axiom.vault.crypto import ENV_VAR


def main() -> None:
    parser = argparse.ArgumentParser(description="Real connector ingest pass.")
    parser.add_argument("--db-url", default="sqlite:///./axiom.db")
    args = parser.parse_args()

    load_axiom_env()
    if not os.environ.get(ENV_VAR):
        print(
            f"[seed_real] vault is LOCKED ({ENV_VAR} not set). Connector secrets "
            f"cannot be decrypted, so no real sync can run. Set {ENV_VAR} and retry.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    engine = create_engine(args.db_url, future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True)
    broadcaster = EventBroadcaster()

    print(f"[seed_real] running real connector sync against {args.db_url} ...")
    summary = asyncio.run(sync_all_connected_connectors(session_local, broadcaster))

    if summary.get("skipped"):
        print(f"[seed_real] skipped: {summary['skipped']} (no real sync ran).")
        return

    results = summary.get("results", [])
    if not results:
        print(
            "[seed_real] no enabled connectors found. Configure + authorize at "
            "least one connector first (Settings -> Integrations)."
        )
        return

    total = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        vendor = result.get("vendor", "?")
        if "error" in result:
            print(f"[seed_real]   {vendor}: ERROR - {result['error']}")
            continue
        ingested = int(result.get("ingested", result.get("events", 0)) or 0)
        total += ingested
        print(f"[seed_real]   {vendor}: ingested {ingested}")
    print(f"[seed_real] done. total ingested across connectors: {total}")


if __name__ == "__main__":
    main()
