"""
test_frontend_routes.py
========================
Automated Test Suite for Frontend HTML Pages and Static Assets.
"""

import sys
from pathlib import Path
from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.main import app
from core.logger import get_logger

log = get_logger("test_frontend")
client = TestClient(app)


def test_frontend_rendering():
    log.info("=" * 90)
    log.info("🧪 [FRONTEND ROUTES TEST SUITE] Testing Admin Desktop & User Mobile Web Apps...")
    log.info("=" * 90)

    # 1. Test Static CSS Asset
    log.info("1️⃣ Testing GET /static/css/styles.css...")
    r = client.get("/static/css/styles.css")
    assert r.status_code == 200
    assert "Plus Jakarta Sans" in r.text
    log.info("   -> Result: PASSED (Design System CSS Loaded)")

    r = client.get("/static/theme.js")
    assert r.status_code == 200
    assert "foodmaster-theme" in r.text

    # 2. Test Admin Desktop Login & Dashboard Page Routes
    log.info("\n2️⃣ Testing GET /admin/login (Admin Login Page)...")
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert "FoodMaster Admin" in r.text

    # Login as admin to get cookie
    login_resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "Admin@123"})
    assert login_resp.status_code == 200

    log.info("   Testing GET /admin/dashboard (Admin Operasional & Settings)...")
    r = client.get("/admin/dashboard", follow_redirects=True)
    assert r.status_code == 200
    assert "FoodMaster Admin" in r.text
    log.info("   -> Result: PASSED (Desktop Admin Dashboard Rendered)")

    log.info("   Testing GET /admin/bot (Admin Bot Activity Dashboard)...")
    r = client.get("/admin/bot", follow_redirects=True)
    assert r.status_code == 200
    assert "Aktivitas bot" in r.text
    log.info("   -> Result: PASSED (Desktop Admin Bot Activity Dashboard Rendered)")

    # 3. Test User Mobile Page Route (/app)
    log.info("\n3️⃣ Testing GET /app (User Mobile Dashboard)...")
    r = client.get("/app")
    assert r.status_code == 200
    assert "FoodMaster Auto-Open" in r.text
    log.info("   -> Result: PASSED (Mobile User HTML Rendered)")

    # 4. Test User Mobile Mitra Slug Route (/mitra/fando-demo)
    log.info("\n4️⃣ Testing GET /mitra/fando-demo (User Link Slug)...")
    r = client.get("/mitra/fando-demo")
    assert r.status_code == 200
    assert "FoodMaster Auto-Open" in r.text
    log.info("   -> Result: PASSED (Mitra Slug Route Rendered)")

    print("\n" + "=" * 90)
    log.info("🎉 ALL FRONTEND WEB ROUTES AND ASSETS TESTED AND PASSED 100%!")
    print("=" * 90)


if __name__ == "__main__":
    test_frontend_rendering()
