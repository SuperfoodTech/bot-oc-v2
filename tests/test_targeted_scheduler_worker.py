"""Unit tests for Targeted Store Execution & Dual-Speed Scheduler."""

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "main-bot" / "src"))

from core.sheets import MerchantOutlet
from scheduler import build_queue, select_next_group
import worker

WIB = ZoneInfo("Asia/Jakarta")
SCHEDULE = {
    day: ["08:00-22:00"]
    for day in ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
}


def make_outlet(store_id: str, portal: str = "Portal A", status_utama: str = "ON", status_aktual: str = "ON", **overrides):
    outlet = MerchantOutlet(
        username="auto7313",
        nama_portal=portal,
        store_id=store_id,
        nama_panjang_outlet=f"Store {store_id}",
        status_utama=status_utama,
        status_aktual=status_aktual,
        regular_hours=SCHEDULE,
        shopee_regular_hours=SCHEDULE,
        schedule_fetch_status="READY",
        status_langganan="Aktif",
        penangguhan="Tidak",
    )
    for k, v in overrides.items():
        setattr(outlet, k, v)
    return outlet


def test_scheduler_identifies_actionable_store_ids():
    now = datetime(2026, 8, 31, 10, 0, tzinfo=WIB)  # Inside operating hours
    outlets = [
        make_outlet("store-1", "Portal 1", status_aktual="ON"),       # In sync
        make_outlet("store-2", "Portal 1", status_aktual="CLOSED"),   # Actionable OPEN!
        make_outlet("store-3", "Portal 2", status_aktual="ON"),       # In sync
    ]
    queue = build_queue(outlets, now)
    portal1 = next(item for item in queue if item.portal_name == "Portal 1")
    portal2 = next(item for item in queue if item.portal_name == "Portal 2")

    assert portal1.actionable_count == 1
    assert portal1.actionable_store_ids == ("store-2",)
    assert portal2.actionable_count == 0
    assert portal2.actionable_store_ids == ()

    # Priority selection must pick Portal 1 first
    selected = select_next_group(queue, now)
    assert selected is not None
    assert selected.portal_name == "Portal 1"
    assert selected.actionable_store_ids == ("store-2",)


def test_worker_sync_all_stores_filters_target_store_ids():
    outlets = [
        make_outlet("store-1", "Portal 1", status_aktual="ON"),
        make_outlet("store-2", "Portal 1", status_aktual="CLOSED"),
        make_outlet("store-3", "Portal 1", status_aktual="ON"),
    ]

    with patch.object(worker.db, "fetch_merchant_outlets_from_db", return_value=outlets), \
         patch.object(worker.browser, "get_session", return_value=None), \
         patch.object(worker.store_status, "get_actual_store_status") as mock_live:
        
        # When target_store_ids is {'store-2'}, only store-2 should be processed
        res = worker.sync_all_stores(
            execute_actions=False,
            target_groups={("auto7313", "Portal 1")},
            target_store_ids={"store-2"},
        )
        assert res["success"] is True
        assert res["total_stores_processed"] == 1


def test_worker_skips_schedule_fetch_when_already_ready():
    outlet = make_outlet("store-1", "Portal 1", status_aktual="ON")
    outlet.schedule_fetch_status = "READY"
    outlet.shopee_regular_hours = SCHEDULE

    mock_driver = MagicMock()
    mock_driver.current_url = "https://partner.shopee.co.id/portal"

    with patch.object(worker.db, "fetch_merchant_outlets_from_db", return_value=[outlet]), \
         patch.dict(worker.ACTIVE_SESSIONS, {"auto7313": {"driver": mock_driver, "shopee_tob_token": "token"}}), \
         patch.object(worker.store_status, "ensure_business_hours_page", return_value=True), \
         patch.object(worker.store_status, "get_regular_hours") as mock_get_reg_hours, \
         patch.object(worker.store_status, "get_special_hours") as mock_get_sp_hours, \
         patch.object(worker.store_status, "get_actual_store_status", return_value={"status_str": "OPEN", "timezone": "Asia/Jakarta"}):
        
        res = worker.sync_all_stores(
            execute_actions=False,
            target_groups={("auto7313", "Portal 1")},
            force_schedule_refresh=False,
        )
        assert res["success"] is True
        # get_regular_hours and get_special_hours should NOT be called since schedule is already READY
        mock_get_reg_hours.assert_not_called()
        mock_get_sp_hours.assert_not_called()
