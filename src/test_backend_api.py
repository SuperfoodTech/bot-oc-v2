"""
test_backend_api.py
===================
Automated Test Suite for FoodMaster Backend REST API Endpoints.
Tests: GET /health, GET /stores, POST /toggle, POST /sync, GET /logs
"""

import sys
import time
from pathlib import Path
from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from backend.main import app
from core.logger import get_logger

log = get_logger("test_backend")
client = TestClient(app)


def test_backend_endpoints():
    log.info("=" * 80)
    log.info("🧪 [BACKEND API TEST SUITE] Starting endpoint testing...")
    log.info("=" * 80)

    # 1. Test Health Endpoint
    log.info("1️⃣ Testing GET /api/v1/health...")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    log.info(f"   -> Result: PASSED (Service: {data['service']})")

    # 2. Test Stores List Endpoint
    log.info("\n2️⃣ Testing GET /api/v1/stores...")
    resp = client.get("/api/v1/stores")
    assert resp.status_code == 200
    stores = resp.json()
    assert len(stores) > 0
    log.info(f"   -> Result: PASSED (Loaded {len(stores)} store(s) in DB)")

    target_store = stores[0]["store_id"]
    log.info(f"   -> Selected target store for testing: Store ID {target_store} ({stores[0]['store_name']})")

    # 3. Test Detail Store Endpoint
    log.info(f"\n3️⃣ Testing GET /api/v1/stores/{target_store}...")
    resp = client.get(f"/api/v1/stores/{target_store}")
    assert resp.status_code == 200
    store_detail = resp.json()
    assert store_detail["store_id"] == target_store
    log.info(f"   -> Result: PASSED (Vercel Status: {store_detail['vercel_status']})")

    # 4. Test Toggle Status Endpoint (OFF)
    log.info(f"\n4️⃣ Testing POST /api/v1/toggle (Set Vercel OFF for 30m)...")
    toggle_payload = {
        "store_id": target_store,
        "status": "OFF",
        "pause_duration_minutes": 30
    }
    resp = client.post("/api/v1/toggle", json=toggle_payload)
    assert resp.status_code == 200
    toggle_data = resp.json()
    assert toggle_data["new_vercel_status"] == "OFF"
    log.info(f"   -> Result: PASSED (New Status: OFF, Pause Until: {toggle_data['pause_until']})")

    # 5. Test Toggle Status Endpoint (ON)
    log.info(f"\n5️⃣ Testing POST /api/v1/toggle (Set Vercel ON)...")
    toggle_payload_on = {
        "store_id": target_store,
        "status": "ON"
    }
    resp = client.post("/api/v1/toggle", json=toggle_payload_on)
    assert resp.status_code == 200
    toggle_on_data = resp.json()
    assert toggle_on_data["new_vercel_status"] == "ON"
    log.info(f"   -> Result: PASSED (New Status: ON)")

    # 6. Test Sync Trigger Endpoint
    log.info("\n6️⃣ Testing POST /api/v1/sync (Dry-run sync loop)...")
    resp = client.post("/api/v1/sync?execute=false")
    assert resp.status_code == 200
    sync_data = resp.json()
    assert sync_data["success"] is True
    log.info(f"   -> Result: PASSED (Processed {sync_data['total_stores_processed']} store(s))")

    # 7. Test Audit Logs Endpoint
    log.info("\n7️⃣ Testing GET /api/v1/logs...")
    resp = client.get("/api/v1/logs?limit=10")
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) > 0
    log.info(f"   -> Result: PASSED (Retrieved {len(logs)} log entry/entries)")
    log.info(f"   -> Latest Log Entry: [{logs[0]['timestamp']}] {logs[0]['action']} - {logs[0]['reason']}")

    print("\n" + "=" * 80)
    log.info("🎉 ALL BACKEND API ENDPOINTS TESTED AND PASSED 100%!")
    print("=" * 80)


if __name__ == "__main__":
    test_backend_endpoints()
