FROM docker.io/library/python:3.12-slim

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

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium

CMD ["uv", "run", "python", "-m", "daemon"]
