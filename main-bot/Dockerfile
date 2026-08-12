# syntax=docker/dockerfile:1.7
# ============================================================
# Dockerfile  –  ShopeeFood Automation Bot Engine
# ============================================================
# Layer-cache strategy:
#   1. System deps + Chromium -> cached permanently with apt mount
#   2. pyproject.toml + lock  -> cached until deps change
#   3. uv sync                -> cached with uv mount (< 2s)
#   4. Source code            -> fast copy, instant rebuild (< 2s)
# ============================================================

FROM python:3.12-slim AS base

# ── 1. System dependencies & Chromium (Permanent Heavy Layer with Cache Mount) ─
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        chromium chromium-driver \
        curl wget gnupg ca-certificates \
        fonts-liberation libasound2 \
        libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
        libnspr4 libnss3 libx11-xcb1 \
        libxcomposite1 libxdamage1 libxrandr2 xdg-utils && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── 2. Copy ONLY dependency manifests (Cache-friendly) ───────
COPY pyproject.toml uv.lock ./

# ── 3. Install deps (Cached with BuildKit uv mount) ───────────
ENV UV_CONCURRENT_DOWNLOADS=1
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ── 4. Copy source code (Instant < 2s rebuild layer) ──────────
COPY src/ ./src/
COPY main-bot/src/ ./main-bot/src/
COPY database/ ./database/
COPY scripts/ ./scripts/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium

CMD ["uv", "run", "python", "main-bot/src/daemon.py"]
