# syntax=docker/dockerfile:1.7
# ============================================================
# Dockerfile.web  –  FastAPI Backend + Admin/User Dashboard
# ============================================================
# Layer-cache strategy:
#   1. System deps           → cached via apt mount
#   2. pyproject.toml + lock → cached via uv mount
#   3. uv sync               → instant cached rebuilds (< 2s)
#   4. Source code            → fast copy layer
# ============================================================

FROM python:3.12-slim AS base

# ── 1. System dependencies (stable layer with cache mount) ────
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── 2. Copy ONLY dependency manifests (cache-friendly) ───────
COPY pyproject.toml uv.lock ./

# ── 3. Install deps (cache mount for uv packages) ─────────────
ENV UV_CONCURRENT_DOWNLOADS=1
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ── 4. Copy source code (fast layer) ──────────────────────────
COPY src/ ./src/
COPY database/ ./database/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

EXPOSE 3001

# Production: single-worker, no reload
CMD ["uv", "run", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "3001"]
