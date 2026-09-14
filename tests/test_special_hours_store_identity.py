import importlib.util
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]


class FakeDriver:
    current_url = (
        "https://partner.shopee.co.id/settings/shopee-food/"
        "business-hours-settings/business-hours?storeId=22403454"
    )

    def __init__(self, response):
        self.response = response

    def execute_script(self, script, store_id):
        return {"url_match": True, "store_match": True, "has_keywords": True}

    def execute_async_script(self, script):
        return self.response


def load_store_status():
    path = ROOT / "src" / "shopee" / "store_status.py"
    spec = importlib.util.spec_from_file_location("store_status_identity_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_special_hours_accepts_matching_store_id():
    module = load_store_status()
    response = {
        "code": 0,
        "msg": "success",
        "data": {
            "store_id": "22403454",
            "special_hours": [
                {
                    "date_start": "2026-03-20",
                    "date_end": "2026-03-20",
                    "intervals": [{"time_from": "08:00", "time_to": "17:00"}],
                    "date_type": 1,
                    "date_desc": "Hari Raya Idul Fitri"
                }
            ]
        }
    }

    result = module.get_special_hours(FakeDriver(response), "22403454")

    assert result == response["data"]
    assert len(result["special_hours"]) == 1
    assert result["special_hours"][0]["date_desc"] == "Hari Raya Idul Fitri"


def test_special_hours_rejects_schedule_from_another_store():
    module = load_store_status()
    response = {
        "code": 0,
        "msg": "success",
        "data": {
            "store_id": "99999999",
            "special_hours": [{"date_start": "2026-03-20", "date_end": "2026-03-20"}]
        }
    }

    with pytest.raises(module.StoreIdentityMismatch) as excinfo:
        module.get_special_hours(FakeDriver(response), "22403454")

    assert "special-hours" in str(excinfo.value)
    assert "requested=22403454" in str(excinfo.value)
    assert "response=99999999" in str(excinfo.value)


def test_special_hours_rejects_missing_store_id():
    module = load_store_status()
    response = {
        "code": 0,
        "msg": "success",
        "data": {
            "special_hours": [{"date_start": "2026-03-20", "date_end": "2026-03-20"}]
        }
    }

    with pytest.raises(module.StoreIdentityMismatch):
        module.get_special_hours(FakeDriver(response), "22403454")


def test_special_hours_returns_none_on_error_code():
    module = load_store_status()
    response = {"code": -1, "msg": "Client timeout (5s)"}

    result = module.get_special_hours(FakeDriver(response), "22403454")
    assert result is None
