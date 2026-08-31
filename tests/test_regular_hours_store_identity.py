import importlib.util
from pathlib import Path


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


def test_regular_hours_accepts_matching_store_id():
    module = load_store_status()
    response = {"code": 0, "data": {"store_id": "22403454", "regular_hours": []}}

    result = module.get_regular_hours(FakeDriver(response), "22403454")

    assert result == response["data"]


def test_regular_hours_rejects_schedule_from_another_store():
    module = load_store_status()
    response = {"code": 0, "data": {"store_id": "22299059", "regular_hours": [{"day": 1}]}}

    try:
        module.get_regular_hours(FakeDriver(response), "22403454")
    except module.StoreIdentityMismatch as exc:
        assert "regular-hours" in str(exc)
    else:
        raise AssertionError("mismatched store response must be rejected")


def test_regular_hours_rejects_missing_store_id():
    module = load_store_status()
    response = {"code": 0, "data": {"regular_hours": [{"day": 1}]}}

    try:
        module.get_regular_hours(FakeDriver(response), "22403454")
    except module.StoreIdentityMismatch:
        pass
    else:
        raise AssertionError("missing response store id must be rejected")


def test_live_status_rejects_another_store_response():
    module = load_store_status()
    response = {
        "code": 0,
        "data": {
            "store": {"id": "22299059"},
            "opening_status": {"display_opening_status": 2, "order_enabled": 1},
        },
    }

    result = module.get_actual_store_status(FakeDriver(response), "22403454")

    assert result is None
