#!/usr/bin/env bash
# ============================================================
# scripts/prod.sh  –  Build & deploy production containers
# ============================================================
# Auto-prunes old containers & dangling images before rebuild.
# Uses Docker BuildKit cache for instant rebuilds.
# ============================================================
set -euo pipefail

PROJECT="fm"
COMPOSE_FILE="docker-compose.prod.yml"

echo "══════════════════════════════════════════════"
echo "  FoodMaster PROD  –  Build & Deploy"
echo "══════════════════════════════════════════════"

# 1. Stop & remove old containers for this project
echo "[1/4] Stopping old containers..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT" down --remove-orphans 2>/dev/null || true

# 2. Prune dangling images & stopped containers
echo "[2/4] Pruning old images & containers..."
docker container prune -f 2>/dev/null || true
docker image prune -f 2>/dev/null || true

# 3. Build with cache (only re-runs layers that changed)
echo "[3/4] Building production images (cached layers reused)..."
DOCKER_BUILDKIT=1 docker compose -f "$COMPOSE_FILE" -p "$PROJECT" build

# 4. Start services (detached)
echo "[4/4] Deploying production services..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT" up -d

echo ""
echo "══════════════════════════════════════════════"
echo "  PROD deployed!"
echo "  Web dashboard : http://localhost:8080"
echo "  Health check  : curl http://localhost:8080/api/v1/health"
echo "  Logs          : docker compose -f $COMPOSE_FILE -p $PROJECT logs -f"
echo "══════════════════════════════════════════════"
