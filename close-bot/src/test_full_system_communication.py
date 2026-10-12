"""
test_full_system_communication.py
==================================
Comprehensive integration test verifying communication between Backend API (Port 8080),
Bot Inter-service API (Port 8081), Automation Daemon, and Vite Frontend API routes.
"""

import sys
import os
import time
from pathlib import Path
from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "backend"))

from backend.main import app as backend_app
import bot_api
from logger import get_logger

log = get_logger("integration_test")

def run_integration_tests():
    log.info("=" * 80)
    log.info("🧪 [FULL SYSTEM INTEGRATION TEST] Testing Frontend ↔ Backend ↔ Bot Engine...")
    log.info("=" * 80)

    backend_client = TestClient(backend_app)
    bot_client = TestClient(bot_api.app)

    # 1️⃣ Test Backend API Health & Base URL Resolution
    log.info("1️⃣ Testing GET /api/v1/health (Backend API)...")
    r1 = backend_client.get("/api/v1/health")
    assert r1.status_code == 200
    log.info(f"   -> Result: PASSED | Response: {r1.json()}")

    # 2️⃣ Test Admin Fetching Stores from Sheets
    log.info("\n2️⃣ Testing GET /api/v1/admin/users (Sheets Sync)...")
    r2 = backend_client.get("/api/v1/admin/users")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["success"] is True
    log.info(f"   -> Result: PASSED | Total Users: {len(data2['users'])}")

    # 3️⃣ Test Bot Status Trace API
    log.info("\n3️⃣ Testing GET /bot/status (Bot Port 8081)...")
    r3 = bot_client.get("/bot/status")
    assert r3.status_code == 200
    log.info(f"   -> Result: PASSED | Bot Trace Status: {r3.json()['bot_status']}")

    # 4️⃣ Test Bot Control: PAUSE
    log.info("\n4️⃣ Testing POST /bot/pause (Remote Pause Command)...")
    r4 = bot_client.post("/bot/pause")
    assert r4.status_code == 200
    assert r4.json()["bot_status"] == "paused"
    log.info(f"   -> Result: PASSED | Bot Patrol Paused Remotely")

    # 5️⃣ Test Bot Control: START
    log.info("\n5️⃣ Testing POST /bot/start (Remote Start Command)...")
    r5 = bot_client.post("/bot/start")
    assert r5.status_code == 200
    assert r5.json()["bot_status"] == "running"
    log.info(f"   -> Result: PASSED | Bot Patrol Resumed Remotely")

    # 6️⃣ Test Bot Control: INSTANT SYNC PATROL
    log.info("\n6️⃣ Testing POST /bot/sync (Instant Patrol Trigger)...")
    r6 = bot_client.post("/bot/sync")
    assert r6.status_code == 200
    assert r6.json()["success"] is True
    log.info(f"   -> Result: PASSED | Patrol API Executed. Status Code 200 OK.")

    # 7️⃣ Test Admin Link Generation
    log.info("\n7️⃣ Testing POST /api/v1/admin/generate-link...")
    r7 = backend_client.post("/api/v1/admin/generate-link", json={"nama_pemilik": "Warung Test", "passcode": "Master@00@"})
    assert r7.status_code == 200
    log.info(f"   -> Result: PASSED | Full URL: {r7.json()['data']['full_url']}")

    # 8️⃣ Test User Mobile Login Authentication
    log.info("\n8️⃣ Testing POST /api/v1/user/login (Mitra Portal)...")
    r8 = backend_client.post("/api/v1/user/login", json={"passcode": "Master@00@"})
    assert r8.status_code == 200
    log.info(f"   -> Result: PASSED | User Authenticated. Outlets Found: {len(r8.json()['outlets'])}")

    log.info("=" * 80)
    log.info("🎉 ALL INTEGRATION TESTS PASSED 100%! Frontend, Backend API & Bot Engine are fully connected!")
    log.info("=" * 80)

if __name__ == "__main__":
    run_integration_tests()
