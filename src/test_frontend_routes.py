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
sys.path.insert(0, str(SCRIPT_DIR))

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
    assert "Anthropic Sans" in r.text
    log.info("   -> Result: PASSED (Design System CSS Loaded)")

    r = client.get("/static/theme.js")
    assert r.status_code == 200
    assert "foodmaster-theme" in r.text

    # 2. Test Admin Desktop Page Route
    log.info("\n2️⃣ Testing GET /admin (Admin Desktop Console)...")
    r = client.get("/admin")
    assert r.status_code == 200
    assert "FoodMaster Admin Console" in r.text
    assert "bootstrap@5.3.8" in r.text
    assert 'id="mobileOutletList"' in r.text
    assert "mobile-outlet-card" in r.text
    assert "table-status" in r.text
    assert "data-theme-toggle" in r.text
    log.info("   -> Result: PASSED (Desktop Admin HTML Rendered)")

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
