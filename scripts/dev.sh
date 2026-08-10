#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

echo "FoodMaster monolith berjalan di http://localhost:3001"
echo "Tekan Ctrl+C untuk berhenti."
echo

APP_BASE_URL="${APP_BASE_URL:-http://localhost:3001}" \
PORT=3001 \
PYTHONPATH="$ROOT_DIR/src" \
exec "$PYTHON_BIN" -m uvicorn backend.main:app --host 0.0.0.0 --port 3001 --reload
