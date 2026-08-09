# ============================================================
# Dockerfile.web  –  FastAPI Backend + Admin/User Dashboard
# ============================================================
# Layer-cache strategy:
#   1. System deps           → almost never changes
#   2. pyproject.toml + lock → changes only when adding deps
#   3. uv sync               → cached until deps change
#   4. Source code            → fast copy, no reinstall
# ============================================================

FROM python:3.12-slim AS base

# ── 1. System dependencies (stable layer) ────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── 2. Copy ONLY dependency manifests (cache-friendly) ───────
COPY pyproject.toml uv.lock ./

# ── 3. Install deps (cached until pyproject/lock changes) ────
RUN uv sync --frozen --no-dev --no-install-project

# ── 4. Copy source code (fast layer, no dep reinstall) ───────
COPY src/ ./src/
COPY database/ ./database/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

COPY web/src/backend/ ./web/src/backend/

EXPOSE 3001

# Production: single-worker, no reload
CMD ["uv", "run", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "3001"]
