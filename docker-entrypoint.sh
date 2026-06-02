#!/bin/sh
# Container entrypoint (P1-8 / P1-10 / P1-11).
#
# Runs the Alembic migrations baked into the image before handing off to the
# CMD (uvicorn). Without this the 6+ migrations shipped in ./alembic are dead
# weight — the schema would only be created by the in-app ensure_*/create_all
# safety net, and Alembic would never be the single source of truth at deploy.
#
# Gated by AXIOM_AUTO_MIGRATE (default "1"). Set AXIOM_AUTO_MIGRATE=0 to skip
# the boot-time migration (e.g. when a separate migration job owns the schema).
set -e

if [ "${AXIOM_AUTO_MIGRATE:-1}" != "0" ]; then
    echo "[entrypoint] running 'alembic upgrade head' (AXIOM_AUTO_MIGRATE=${AXIOM_AUTO_MIGRATE:-1})"
    alembic upgrade head
else
    echo "[entrypoint] skipping migrations (AXIOM_AUTO_MIGRATE=0)"
fi

exec "$@"
