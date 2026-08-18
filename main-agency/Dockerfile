# syntax=docker/dockerfile:1.7
# ============================================================
# Dockerfile  —  Agency Churn Bot Engine (fm-agency)
# ============================================================
# Layer-cache strategy:
#   1. Reuse bot-oc-bot image yang sudah include Chromium
#      → skip download & install (460MB cached, build < 5s)
#   2. pyproject.toml + lock → cached via uv mount
#   3. Source code → fast COPY, < 2s
#
# Build berikutnya HANYA trigger jika:
#   - main-agency/src/ berubah  → hanya layer terakhir rebuild
#   - src/ berubah              → layer 3 rebuild
#   - pyproject.toml/uv.lock    → layer 2 rebuild
#   - TIDAK PERNAH re-download Chromium
# ============================================================

# Gunakan image fm-bot yang sudah include Chromium sebagai base.
# Ini menghilangkan seluruh step apt-get install secara permanen.
FROM bot-oc-bot:latest AS base

WORKDIR /app

# ── 1. Copy dependency manifests (cache trigger jika deps berubah) ────
COPY pyproject.toml uv.lock ./

# ── 2. Install/sync deps (cached dengan BuildKit uv mount) ───────────
ENV UV_CONCURRENT_DOWNLOADS=1
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ── 3. Source code (sering berubah — selalu layer paling akhir) ──────
COPY src/ ./src/
COPY database/ ./database/

# ── 4. Agency-specific entrypoint (paling sering berubah) ────────────
COPY main-agency/src/ ./main-agency/src/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src:/app/main-agency/src
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium
ENV HEADLESS=true

CMD ["uv", "run", "python", "main-agency/src/daemon.py"]
