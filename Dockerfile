# syntax=docker/dockerfile:1

# ---- Stage 1: build the React frontend -> frontend/dist ---------------------
FROM node:20-bookworm-slim AS frontend
WORKDIR /app/frontend
# Install deps against the lockfile for reproducible builds.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
# Build the SPA. `npm run build` -> frontend/dist.
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: python runtime ------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package first (layer-cached unless pyproject/sources change).
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install .

# Bring in the built SPA so create_app() mounts frontend/dist at "/".
COPY --from=frontend /app/frontend/dist ./frontend/dist
# P1-8: the source-relative parents[] lookup does not work once the package is
# pip-installed into site-packages. Point create_app() at the absolute dist path.
ENV AXIOM_FRONTEND_DIST=/app/frontend/dist

# Alembic migrations (real migration tree is ./alembic).
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

# Synthetic demo fixture: lets `python -m axiom.cli ingest --source synthetic`
# seed a demo brain inside the container (resolved via <cwd>/fixtures).
COPY fixtures/ ./fixtures/

# Entrypoint runs `alembic upgrade head` (gated by AXIOM_AUTO_MIGRATE, default 1)
# before starting uvicorn so the migrations baked into the image are actually
# applied at boot (P1-10/P1-11) instead of being dead weight.
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

# SQLite DB lives in a mounted volume (see docker-compose.yml).
ENV DATABASE_URL=sqlite:////data/axiom.db \
    AXIOM_AUTO_MIGRATE=1
VOLUME ["/data"]

EXPOSE 8000

# Module-level ASGI app (DEP-09): uvicorn axiom.studio.server:app
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "axiom.studio.server:app", "--host", "0.0.0.0", "--port", "8000"]
