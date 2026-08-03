"""
test_full_backend_api.py
========================
Automated Test Suite for Admin Dashboard & User Link Dashboard Backend REST APIs.
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

log = get_logger("test_full_backend")
client = TestClient(app)


def run_full_backend_tests():
    log.info("=" * 90)
    log.info("🧪 [FULL BACKEND API TEST SUITE] Testing Admin & User Link Endpoints...")
    log.info("=" * 90)

    # 1. Healthcheck
    log.info("1️⃣ Testing GET /api/v1/health...")
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    log.info(f"   -> Result: PASSED ({r.json()['service']} v{r.json()['version']})")

    # 2. Admin: List All Users & Outlets
    log.info("\n2️⃣ Testing GET /api/v1/admin/users...")
    r = client.get("/api/v1/admin/users")
    assert r.status_code == 200
    users_data = r.json()["users"]
    assert len(users_data) > 0
    log.info(f"   -> Result: PASSED (Loaded {len(users_data)} user owner group(s))")

    # 3. Admin: Generate Unique User Link
    log.info("\n3️⃣ Testing POST /api/v1/admin/generate-link...")
    link_payload = {"nama_pemilik": "Mitra Budi", "passcode": "Budi@123"}
    r = client.post("/api/v1/admin/generate-link", json=link_payload)
    assert r.status_code == 200
    gen_data = r.json()["data"]
    log.info(f"   -> Result: PASSED (Generated Link: {gen_data['full_url']}, Passcode: {gen_data['passcode']})")

    # 4. Admin: Toggle Suspension Status & Reason
    target_store = "21897166"
    log.info(f"\n4️⃣ Testing POST /api/v1/admin/suspend on Store {target_store}...")
    sus_payload = {
        "store_id": target_store,
        "penangguhan": "Ya",
        "alasan_penangguhan": "Menunggak tagihan bulan Agustus"
    }
    r = client.post("/api/v1/admin/suspend", json=sus_payload)
    assert r.status_code == 200
    sus_res = r.json()
    assert sus_res["penangguhan"] == "Ya"
    log.info(f"   -> Result: PASSED (Suspension set to Ya: {sus_res['alasan_penangguhan']})")

    # 5. Admin: Renew Subscription Expiry Date
    log.info(f"\n5️⃣ Testing POST /api/v1/admin/renew on Store {target_store}...")
    renew_payload = {
        "store_id": target_store,
        "new_expiry_date": "2026-12-31"
    }
    r = client.post("/api/v1/admin/renew", json=renew_payload)
    assert r.status_code == 200
    renew_res = r.json()
    assert renew_res["new_expiry_date"] == "2026-12-31"
    log.info(f"   -> Result: PASSED (Subscription renewed until 2026-12-31)")

    # 6. User Link: Login by Passcode
    log.info("\n6️⃣ Testing POST /api/v1/user/login (Passcode: Master@00@)...")
    r = client.post("/api/v1/user/login", json={"passcode": "Master@00@"})
    assert r.status_code == 200
    login_res = r.json()
    assert login_res["success"] is True
    log.info(f"   -> Result: PASSED (Authenticated as '{login_res['nama_pemilik']}', Total Outlets: {login_res['total_outlets']})")

    # 7. User Link: Get Multi-Outlets
    log.info(f"\n7️⃣ Testing GET /api/v1/user/outlets (Pemilik: Fando)...")
    r = client.get("/api/v1/user/outlets?nama_pemilik=Fando")
    assert r.status_code == 200
    outlets_res = r.json()["outlets"]
    log.info(f"   -> Result: PASSED (Loaded {len(outlets_res)} outlet(s) for Fando)")

    # 8. User Link: Pause Store with Selected Durations (30m, 60m, rest_of_day, custom)
    log.info(f"\n8️⃣ Testing POST /api/v1/user/pause (Duration: 60 Menit)...")
    pause_payload = {
        "store_id": target_store,
        "duration_type": "60_min"
    }
    r = client.post("/api/v1/user/pause", json=pause_payload)
    assert r.status_code == 200
    pause_res = r.json()
    assert pause_res["vercel_status"] == "OFF"
    log.info(f"   -> Result: PASSED (Paused Label: {pause_res['duration_label']}, Until: {pause_res['pause_until']})")

    # 9. User Link: Resume / Open Store
    log.info(f"\n9️⃣ Testing POST /api/v1/user/resume...")
    r = client.post(f"/api/v1/user/resume?store_id={target_store}")
    assert r.status_code == 200
    resume_res = r.json()
    assert resume_res["vercel_status"] == "ON"
    log.info(f"   -> Result: PASSED (Vercel Status: ON)")

    # 10. User Link: Audit Log History for Outlets
    log.info(f"\n🔟 Testing GET /api/v1/user/history for Store {target_store}...")
    r = client.get(f"/api/v1/user/history?store_ids={target_store}")
    assert r.status_code == 200
    history_logs = r.json()["logs"]
    assert len(history_logs) > 0
    log.info(f"   -> Result: PASSED (Retrieved {len(history_logs)} log entry/entries for store {target_store})")
    log.info(f"   -> Latest User Log: [{history_logs[0]['timestamp']}] {history_logs[0]['action']} - {history_logs[0]['reason']}")

    print("\n" + "=" * 90)
    log.info("🎉 ALL ADMIN & USER LINK BACKEND ENDPOINTS TESTED AND PASSED 100%!")
    print("=" * 90)


if __name__ == "__main__":
    run_full_backend_tests()
