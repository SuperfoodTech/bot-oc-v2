#!/usr/bin/env bash
# ============================================================
# scripts/prod.sh  –  Build & deploy production containers
# ============================================================
# Auto-prunes old containers & dangling images after deploy.
# Uses Docker BuildKit cache for instant rebuilds (< 2s).
# ============================================================
set -euo pipefail

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

PROJECT="fm"
COMPOSE_FILE="docker-compose.yml"

if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

echo "══════════════════════════════════════════════"
echo "  FoodMaster PROD  –  Instant Build & Deploy ($COMPOSE_CMD)"
echo "══════════════════════════════════════════════"

# 1. Stop old containers for this project
echo "[1/4] Stopping old containers..."
$COMPOSE_CMD -f "$COMPOSE_FILE" -p "$PROJECT" down 2>/dev/null || true

# 2. Build containers using BuildKit layer cache
echo "[2/4] Building production images with BuildKit layer cache..."
$COMPOSE_CMD -f "$COMPOSE_FILE" -p "$PROJECT" build

# 3. Start services (detached)
echo "[3/4] Deploying production services..."
$COMPOSE_CMD -f "$COMPOSE_FILE" -p "$PROJECT" up -d

# 4. Cleanup dangling images after deployment
echo "[4/4] Cleaning up unused images..."
docker container prune -f 2>/dev/null || true

echo ""
echo "══════════════════════════════════════════════"
echo "  PROD deployed successfully!"
echo "  Monolith app  : http://localhost:3001"
echo "  Health check  : curl http://localhost:3001/api/v1/health"
echo "  Logs          : $COMPOSE_CMD -f $COMPOSE_FILE -p $PROJECT logs -f"
echo "══════════════════════════════════════════════"
