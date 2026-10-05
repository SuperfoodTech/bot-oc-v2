"""
test_toggle_attribution_contract.py
===================================
Contract tests verifying actor attribution across:
1. Agency Admin Toggle (/api/v1/toggle) -> ADMIN_PAUSE_STORE / ADMIN_RESUME_STORE
2. Agency Mitra Toggle (/api/v1/user/pause, /api/v1/user/resume) -> USER_PAUSE_STORE / USER_RESUME_STORE
3. Virtual Brand Admin Toggle (/api/v1/admin/vb/brands/{id}/status) -> ADMIN_PAUSE_STORE / ADMIN_RESUME_STORE
4. Virtual Brand Mitra Toggle (/api/v1/brand/{slug}/toggle) -> USER_PAUSE_STORE / USER_RESUME_STORE
"""

from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import backend.main as main_module


def test_agency_admin_toggle_attribution(monkeypatch):
    client = TestClient(main_module.app)
    login = client.post("/api/v1/admin/login", json={"username": "admin", "password": "Admin@123"})
    assert login.status_code == 200

    captured_toggle = {}

    def fake_get_store(store_id: str):
        return {
            "store_id": store_id,
            "store_name": "Agency Test Store",
            "shopee_regular_hours": {"Senin": ["00:00-23:59"], "Selasa": ["00:00-23:59"], "Rabu": ["00:00-23:59"], "Kamis": ["00:00-23:59"], "Jumat": ["00:00-23:59"], "Sabtu": ["00:00-23:59"], "Minggu": ["00:00-23:59"]},
            "timezone": "Asia/Jakarta",
            "display_toggle_reason": None,
            "schedule_fetch_status": "FETCHED_OK",
            "schedule_available": True,
            "is_suspended": False,
        }

    def fake_apply_admin_toggle(store_id, status, pause_until, action, target_state, reason, pause_mode=None, pause_from=None):
        captured_toggle["store_id"] = store_id
        captured_toggle["status"] = status
        captured_toggle["action"] = action
        captured_toggle["reason"] = reason
        return {
            "success": True,
            "store_id": store_id,
            "vercel_status": status,
            "pause_from": pause_from,
            "pause_until": pause_until,
            "changed_at": "2026-10-05 08:00:00",
        }

    monkeypatch.setattr(main_module.state, "get_store_by_id", fake_get_store)
    monkeypatch.setattr(main_module.state, "apply_admin_toggle", fake_apply_admin_toggle)

    # 1. Admin Pause
    res_pause = client.post("/api/v1/toggle", json={"store_id": "999001", "status": "OFF", "duration_type": "30_min"})
    assert res_pause.status_code == 200
    assert captured_toggle["action"] == "ADMIN_PAUSE_STORE"
    assert "Admin admin" in captured_toggle["reason"]

    # 2. Admin Resume
    res_resume = client.post("/api/v1/toggle", json={"store_id": "999001", "status": "ON"})
    assert res_resume.status_code == 200
    assert captured_toggle["action"] == "ADMIN_RESUME_STORE"
    assert "Admin admin" in captured_toggle["reason"]


def test_agency_mitra_toggle_attribution(monkeypatch):
    client = TestClient(main_module.app)
    captured_toggle = {}

    def fake_get_store(store_id: str):
        return {
            "store_id": store_id,
            "store_name": "Agency Test Store",
            "shopee_regular_hours": {"Senin": ["00:00-23:59"], "Selasa": ["00:00-23:59"], "Rabu": ["00:00-23:59"], "Kamis": ["00:00-23:59"], "Jumat": ["00:00-23:59"], "Sabtu": ["00:00-23:59"], "Minggu": ["00:00-23:59"]},
            "timezone": "Asia/Jakarta",
            "display_toggle_reason": None,
            "schedule_fetch_status": "FETCHED_OK",
            "schedule_available": True,
            "is_suspended": False,
        }

    def fake_apply_user_toggle(store_id, status, pause_until, action, target_state, reason, pause_mode=None, pause_from=None):
        captured_toggle["store_id"] = store_id
        captured_toggle["status"] = status
        captured_toggle["action"] = action
        captured_toggle["reason"] = reason
        return {
            "success": True,
            "code": None,
            "detail": None,
            "store_id": store_id,
            "vercel_status": status,
            "pause_from": pause_from,
            "pause_until": pause_until,
            "changed_at": "2026-10-05 08:00:00",
        }

    monkeypatch.setattr(main_module.state, "get_store_by_id", fake_get_store)
    monkeypatch.setattr(main_module.state, "apply_user_toggle", fake_apply_user_toggle)

    # 1. Mitra Pause
    res_pause = client.post("/api/v1/user/pause", json={"store_id": "999001", "duration_type": "30_min"})
    assert res_pause.status_code == 200
    assert captured_toggle["action"] == "USER_PAUSE_STORE"
    assert "User set store OFF" in captured_toggle["reason"]

    # 2. Mitra Resume
    res_resume = client.post("/api/v1/user/resume?store_id=999001")
    assert res_resume.status_code == 200
    assert captured_toggle["action"] == "USER_RESUME_STORE"
    assert "User manually turned Vercel Toggle ON" in captured_toggle["reason"]


def test_vb_admin_toggle_attribution(monkeypatch):
    client = TestClient(main_module.app)
    login = client.post("/api/v1/admin/login", json={"username": "admin", "password": "Admin@123"})
    assert login.status_code == 200

    brand_id = "22222222-2222-2222-2222-222222222222"
    captured_req = {}

    def fake_request_status(b_id, status, admin_id, pause_until=None, pause_from=None):
        captured_req["brand_id"] = b_id
        captured_req["status"] = status
        captured_req["admin_id"] = admin_id
        return {
            "id": b_id,
            "name": "VB Brand Test",
            "applied_status": "ON",
            "requested_status": status,
            "requested_at": None,
            "requested_pause_from": pause_from,
            "requested_pause_until": pause_until,
        }

    monkeypatch.setattr(main_module.vb, "request_status", fake_request_status)

    res = client.patch(f"/api/v1/admin/vb/brands/{brand_id}/status", json={"status": "PAUSED", "duration_type": "60_min"})
    assert res.status_code == 200
    assert captured_req["status"] == "PAUSED"
    assert captured_req["admin_id"] is not None


def test_vb_mitra_toggle_attribution(monkeypatch):
    client = TestClient(main_module.app)
    slug = "katsunami"
    captured_req = {}

    def fake_get_brand(slug_or_id: str):
        return {
            "id": "33333333-3333-3333-3333-333333333333",
            "name": "Katsunami",
            "slug": "katsunami",
            "is_schedule_locked": False,
            "outlets": [],
        }

    def fake_request_brand_status_public(slug_or_id: str, status: str, pause_until=None, pause_from=None):
        captured_req["slug_or_id"] = slug_or_id
        captured_req["status"] = status
        return {
            "id": "33333333-3333-3333-3333-333333333333",
            "name": "Katsunami",
            "applied_status": "PAUSED",
            "requested_status": status,
            "requested_at": None,
            "requested_pause_from": pause_from,
            "requested_pause_until": pause_until,
        }

    monkeypatch.setattr(main_module.vb, "get_brand_by_slug_or_id", fake_get_brand)
    monkeypatch.setattr(main_module.vb, "request_brand_status_public", fake_request_brand_status_public)

    res = client.post(f"/api/v1/brand/{slug}/toggle", json={"status": "ON"})
    assert res.status_code == 200
    assert captured_req["status"] == "ON"
    assert captured_req["slug_or_id"] == slug
