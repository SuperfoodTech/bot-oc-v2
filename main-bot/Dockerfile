# ============================================================
# Dockerfile  –  ShopeeFood Automation Bot Engine
# ============================================================
# Layer-cache strategy:
#   1. System deps + Chromium -> cached permanently
#   2. pyproject.toml + lock  -> cached until deps change
#   3. uv sync                -> cached until deps change
#   4. Source code            -> fast copy, instant rebuild (< 2s)
# ============================================================

FROM python:3.12-slim AS base

# ── 1. System dependencies & Chromium (Permanent Heavy Layer) ─
RUN apt-get update && \
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

# ── 3. Install deps (Cached until pyproject/lock changes) ────
RUN uv sync --frozen --no-dev --no-install-project

# ── 4. Copy source code (Instant < 2s rebuild layer) ──────────
COPY src/ ./src/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium

CMD ["uv", "run", "python", "-m", "daemon"]
