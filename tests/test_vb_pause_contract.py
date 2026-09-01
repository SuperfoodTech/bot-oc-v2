from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import backend.main as main_module
from backend.vb import pick_pause_reference_outlet


class FixedJakartaDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        current = cls(2026, 8, 31, 21, 0, 0)
        return current if tz is None else current.replace(tzinfo=tz)


def test_pick_pause_reference_outlet_prefers_first_usable_schedule():
    outlet = pick_pause_reference_outlet(
        [
            {
                "store_id": "100",
                "timezone": "Asia/Jakarta",
                "shopee_regular_hours": {},
            },
            {
                "store_id": "200",
                "timezone": "Asia/Jakarta",
                "shopee_regular_hours": {"Selasa": ["07:00-22:00"]},
            },
        ]
    )

    assert outlet is not None
    assert outlet["store_id"] == "200"
    assert outlet["shopee_regular_hours"] == {"Selasa": ["07:00-22:00"]}


def test_vb_rest_of_day_uses_reference_outlet_schedule(monkeypatch):
    client = TestClient(main_module.app)
    login = client.post("/api/v1/admin/login", json={"username": "admin", "password": "Admin@123"})
    assert login.status_code == 200

    brand_id = "11111111-1111-1111-1111-111111111111"
    captured: dict[str, object] = {}

    def fake_brand_detail(requested_brand_id: str):
        assert requested_brand_id == brand_id
        return {
            "id": brand_id,
            "name": "VB Test",
            "outlets": [
                {
                    "store_id": "100",
                    "timezone": "Asia/Jakarta",
                    "shopee_regular_hours": {},
                },
                {
                    "store_id": "200",
                    "timezone": "Asia/Jakarta",
                    "shopee_regular_hours": {"Selasa": ["07:00-22:00"]},
                },
            ],
        }

    def fake_request_status(requested_brand_id: str, status: str, admin_id: str, pause_until=None):
        captured["brand_id"] = requested_brand_id
        captured["status"] = status
        captured["admin_id"] = admin_id
        captured["pause_until"] = pause_until
        return {
            "id": requested_brand_id,
            "name": "VB Test",
            "applied_status": "ON",
            "requested_status": status,
            "requested_at": None,
            "requested_pause_until": pause_until,
        }

    monkeypatch.setattr(main_module.vb, "brand_detail", fake_brand_detail)
    monkeypatch.setattr(main_module.vb, "request_status", fake_request_status)
    monkeypatch.setattr(main_module, "datetime", FixedJakartaDateTime)

    response = client.patch(
        f"/api/v1/admin/vb/brands/{brand_id}/status",
        json={"status": "PAUSED", "duration_type": "rest_of_day"},
    )

    assert response.status_code == 200
    assert captured["brand_id"] == brand_id
    assert captured["status"] == "PAUSED"
    assert captured["pause_until"] == datetime(2026, 9, 1, 7, 0, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
