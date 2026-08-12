#!/usr/bin/env bash
# ============================================================
# scripts/prod.sh  –  Build & deploy production containers
# ============================================================
# Auto-prunes old containers & dangling images before rebuild.
# Supports both docker-compose (v1) and docker compose (v2).
# ============================================================
set -euo pipefail

PROJECT="fm"
COMPOSE_FILE="docker-compose.yml"

if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

echo "══════════════════════════════════════════════"
echo "  FoodMaster PROD  –  Build & Deploy ($COMPOSE_CMD)"
echo "══════════════════════════════════════════════"

# 1. Stop & remove old containers for this project
echo "[1/4] Stopping old containers..."
$COMPOSE_CMD -f "$COMPOSE_FILE" -p "$PROJECT" down 2>/dev/null || true

# 2. Prune dangling images & stopped containers
echo "[2/4] Pruning old images & containers..."
docker container prune -f 2>/dev/null || true
docker image prune -f 2>/dev/null || true

# 3. Build containers
echo "[3/4] Building production images..."
$COMPOSE_CMD -f "$COMPOSE_FILE" -p "$PROJECT" build

# 4. Start services (detached)
echo "[4/4] Deploying production services..."
$COMPOSE_CMD -f "$COMPOSE_FILE" -p "$PROJECT" up -d

echo ""
echo "══════════════════════════════════════════════"
echo "  PROD deployed!"
echo "  Monolith app  : http://localhost:3001"
echo "  Health check  : curl http://localhost:3001/api/v1/health"
echo "  Logs          : $COMPOSE_CMD -f $COMPOSE_FILE -p $PROJECT logs -f"
echo "══════════════════════════════════════════════"
