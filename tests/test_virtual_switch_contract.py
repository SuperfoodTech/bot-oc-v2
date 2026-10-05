import pytest
from unittest.mock import MagicMock, call
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_store_status():
    path = ROOT / "src" / "shopee" / "store_status.py"
    spec = importlib.util.spec_from_file_location("store_status_vs_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MockShopeeDriver:
    def __init__(self, current_url="https://partner.shopee.co.id/portal", async_response=None):
        self.current_url = current_url
        self.async_response = async_response or {"code": 0, "data": {}}
        self.script_calls = []
        self.async_script_calls = []
        self.navigated_urls = []

    def get(self, url):
        self.navigated_urls.append(url)
        self.current_url = url

    def execute_script(self, script, *args):
        self.script_calls.append({"script": script, "args": args})
        return {"url_match": True, "store_match": True, "has_keywords": True}

    def execute_async_script(self, script):
        self.async_script_calls.append(script)
        if callable(self.async_response):
            return self.async_response(script)
        return self.async_response


def test_is_on_shopee_partner():
    module = load_store_status()
    driver_partner = MockShopeeDriver("https://partner.shopee.co.id/dashboard")
    driver_foody = MockShopeeDriver("https://foody.shopee.co.id/api/seller")
    driver_blank = MockShopeeDriver("about:blank")
    driver_other = MockShopeeDriver("https://google.com")

    assert module.is_on_shopee_partner(driver_partner) is True
    assert module.is_on_shopee_partner(driver_foody) is True
    assert module.is_on_shopee_partner(driver_blank) is False
    assert module.is_on_shopee_partner(driver_other) is False
    assert module.is_on_shopee_partner(None) is False


def test_switch_store_context_injects_cookie():
    module = load_store_status()
    driver = MockShopeeDriver("https://partner.shopee.co.id/settings")

    result = module.switch_store_context(driver, "1146482")

    assert result is True
    assert len(driver.navigated_urls) == 0  # Zero DOM navigation!
    assert len(driver.script_calls) == 1
    script_entry = driver.script_calls[0]
    assert script_entry["args"][0] == "1146482"
    assert "shopee_foody_mid" in script_entry["script"]
    assert "shopee_tob_entity_id" in script_entry["script"]

    # Test with explicit merchant_id
    res_mid = module.switch_store_context(driver, "21897166", merchant_id="14367488")
    assert res_mid is True
    assert driver.script_calls[1]["args"] == ("21897166", "14367488")


def test_switch_store_context_navigates_if_not_on_portal():
    module = load_store_status()
    driver = MockShopeeDriver("about:blank")

    result = module.switch_store_context(driver, "1146482")

    assert result is True
    assert len(driver.navigated_urls) == 1
    assert "storeId=1146482" in driver.navigated_urls[0]


def test_get_actual_store_status_virtual_switch_success():
    module = load_store_status()
    response = {
        "code": 0,
        "data": {
            "store": {"id": "1146482", "name": "Katsunami Grogol"},
            "opening_status": {
                "display_opening_status": 2,
                "order_enabled": 1,
                "pause_time": {"pause_start_time": 0},
            },
        },
    }
    driver = MockShopeeDriver("https://partner.shopee.co.id/portal", async_response=response)

    res = module.get_actual_store_status(driver, "1146482")

    assert res is not None
    assert res["status_str"] == "OPEN"
    assert res["store_name"] == "Katsunami Grogol"
    assert len(driver.navigated_urls) == 0  # No driver.get() called!
    assert len(driver.async_script_calls) == 1
    assert "targetSid = \"1146482\"" in driver.async_script_calls[0]
    assert "shopee_foody_mid" in driver.async_script_calls[0]


def test_get_actual_store_status_fallback_on_mismatch():
    module = load_store_status()
    call_count = 0

    def dynamic_response(script):
        nonlocal call_count
        call_count += 1
        # On first call (virtual switch), return mismatch. On second call (after fallback nav), return matching
        if call_count == 1:
            return {
                "code": 0,
                "data": {"store": {"id": "9999999"}, "opening_status": {"display_opening_status": 3}},
            }
        return {
            "code": 0,
            "data": {
                "store": {"id": "1146482", "name": "Katsunami Grogol"},
                "opening_status": {"display_opening_status": 2, "order_enabled": 1},
            },
        }

    driver = MockShopeeDriver("https://partner.shopee.co.id/portal", async_response=dynamic_response)

    res = module.get_actual_store_status(driver, "1146482")

    assert res is not None
    assert res["status_str"] == "OPEN"
    assert len(driver.navigated_urls) == 1  # Fallback triggered navigation
    assert "storeId=1146482" in driver.navigated_urls[0]


def test_get_regular_hours_virtual_switch():
    module = load_store_status()
    response = {
        "code": 0,
        "data": {
            "store_id": "1146482",
            "regular_hours": [{"day": 1, "intervals": [{"start": 36000, "end": 72000}]}],
        },
    }
    driver = MockShopeeDriver("https://partner.shopee.co.id/portal", async_response=response)

    data = module.get_regular_hours(driver, "1146482")

    assert data is not None
    assert data["store_id"] == "1146482"
    assert len(driver.navigated_urls) == 0  # Instant virtual switch!


def test_get_special_hours_virtual_switch():
    module = load_store_status()
    response = {
        "code": 0,
        "data": {
            "store_id": "1146482",
            "special_hours": [{"date": 1789321159, "status": 2}],
        },
    }
    driver = MockShopeeDriver("https://partner.shopee.co.id/portal", async_response=response)

    data = module.get_special_hours(driver, "1146482")

    assert data is not None
    assert data["store_id"] == "1146482"
    assert len(driver.navigated_urls) == 0


def test_pause_and_open_store_actions_virtual_switch():
    module = load_store_status()
    driver = MockShopeeDriver("https://partner.shopee.co.id/portal", async_response={"code": 0, "msg": "success"})

    # Test open action
    open_ok = module.open_store_action(driver, "1146482")
    assert open_ok is True
    assert len(driver.navigated_urls) == 0
    assert 'targetSid = "1146482"' in driver.async_script_calls[-1]
    assert "action/open?store_id=' + targetSid" in driver.async_script_calls[-1]

    # Test pause action
    pause_ok = module.pause_store_action(driver, "1146482", pause_duration_minutes=60)
    assert pause_ok is True
    assert len(driver.navigated_urls) == 0
    assert 'targetSid = "1146482"' in driver.async_script_calls[-1]
    assert "action/pause?store_id=' + targetSid" in driver.async_script_calls[-1]


def test_zero_context_bleeding_across_consecutive_outlets():
    module = load_store_status()
    driver = MockShopeeDriver("https://partner.shopee.co.id/portal")

    stores = ["10001", "10002", "10003", "10004"]
    for sid in stores:
        driver.async_response = {
            "code": 0,
            "data": {
                "store": {"id": sid, "name": f"Store {sid}"},
                "opening_status": {"display_opening_status": 2, "order_enabled": 1},
            },
        }
        res = module.get_actual_store_status(driver, sid)
        assert res is not None
        assert res["store_name"] == f"Store {sid}"
        # Verify script injected exact store ID
        last_script = driver.async_script_calls[-1]
        assert f'targetSid = "{sid}"' in last_script
