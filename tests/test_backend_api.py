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
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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

    # Admin Login
    login_resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "Admin@123"})
    assert login_resp.status_code == 200

    # 2. Test Stores List Endpoint
    log.info("\n2️⃣ Testing GET /api/v1/stores...")
    resp = client.get("/api/v1/stores")
    assert resp.status_code == 200
    stores = resp.json()
    assert len(stores) > 0
    log.info(f"   -> Result: PASSED (Loaded {len(stores)} store(s) in DB)")

    target_store = stores[0]["store_id"]
    log.info(f"   -> Selected target store for testing: Store ID {target_store} ({stores[0]['store_name']})")

    # Reset suspension status for test target store
    client.post("/api/v1/admin/suspend", json={"store_id": target_store, "penangguhan": "Tidak", "alasan_penangguhan": "Aktif kembali"})

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
    if resp.status_code == 403:
        assert "di luar jadwal operasional" in resp.json()["detail"].lower()
        log.info("   -> Result: PASSED (Toggle correctly locked outside operating schedule)")
        return
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

    # 7. Test Get Audit Logs
    log.info(f"\n7️⃣ Testing GET /api/v1/logs...")
    resp = client.get("/api/v1/logs")
    assert resp.status_code == 200
    logs = resp.json()
    assert isinstance(logs, list)
    log.info(f"   -> Result: PASSED (Retrieved {len(logs)} log entry/entries)")
    if logs:
        log.info(f"   -> Latest Log Entry: [{logs[0]['timestamp']}] {logs[0]['action']} - {logs[0]['reason']}")

    # 8. Test Get Bot Status Endpoint
    log.info(f"\n8️⃣ Testing GET /api/v1/admin/bot-status...")
    resp = client.get("/api/v1/admin/bot-status")
    assert resp.status_code == 200
    bot_status = resp.json()
    assert "is_online" in bot_status
    assert "status_text" in bot_status
    log.info(f"   -> Result: PASSED (Bot Status: {bot_status['status_text']} | Detail: {bot_status['detail_text']})")

    # 9. Test POST /api/v1/admin/bot/control (Start, Pause, Sync)
    log.info(f"\n9️⃣ Testing POST /api/v1/admin/bot/control (Start, Pause, Sync)...")
    ctrl_pause = client.post("/api/v1/admin/bot/control", json={"action": "pause"})
    assert ctrl_pause.status_code == 200
    assert ctrl_pause.json()["success"] is True
    log.info(f"   -> Pause Action: PASSED ({ctrl_pause.json()['message']})")

    ctrl_start = client.post("/api/v1/admin/bot/control", json={"action": "start"})
    assert ctrl_start.status_code == 200
    assert ctrl_start.json()["success"] is True
    log.info(f"   -> Start Action: PASSED ({ctrl_start.json()['message']})")

    ctrl_sync = client.post("/api/v1/admin/bot/control", json={"action": "sync"})
    assert ctrl_sync.status_code == 200
    assert ctrl_sync.json()["success"] is True
    log.info(f"   -> Sync Action: PASSED ({ctrl_sync.json()['message']})")

    print("\n" + "=" * 80)
    log.info("🎉 ALL BACKEND API ENDPOINTS TESTED AND PASSED 100%!")
    print("=" * 80)


if __name__ == "__main__":
    test_backend_endpoints()
