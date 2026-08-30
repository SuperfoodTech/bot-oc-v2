from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "main-bot" / "src"))

from core.sheets import MerchantOutlet
from scheduler import build_queue, derive_outlet_due, select_next_group


WIB = ZoneInfo("Asia/Jakarta")
SCHEDULE = {
    day: ["12:00-13:40", "14:00-15:00"]
    for day in ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
}


def outlet(**overrides):
    value = MerchantOutlet(
        username="auto7313",
        nama_portal="Merchant A",
        store_id="store-1",
        nama_panjang_outlet="Outlet 1",
        status_utama="ON",
        status_aktual="ON",
        regular_hours=SCHEDULE,
        shopee_regular_hours=SCHEDULE,
        status_langganan="Aktif",
        penangguhan="Tidak",
    )
    for key, item in overrides.items():
        setattr(value, key, item)
    return value


def test_random_shopee_close_is_due_immediately_and_beats_heartbeat():
    now = datetime(2026, 8, 31, 12, 30, tzinfo=WIB)  # Monday, inside session 1
    state = derive_outlet_due(outlet(status_aktual="CLOSED"), now)

    assert state.priority == 100
    assert state.actionable is True
    assert state.due_at == now


def test_pause_boundary_targets_second_session_before_pause_expiry():
    now = datetime(2026, 8, 31, 13, 30, tzinfo=WIB)
    state = derive_outlet_due(
        outlet(status_utama="OFF", status_aktual="PAUSE", pause_until="2026-08-31 14:30:00"),
        now,
    )

    assert state.priority == 80
    assert state.due_at == datetime(2026, 8, 31, 14, 0, tzinfo=WIB)


def test_same_merchant_outlets_are_aggregated_into_one_queue_item():
    now = datetime(2026, 8, 31, 12, 30, tzinfo=WIB)
    queue = build_queue([
        outlet(store_id="store-1", status_aktual="CLOSED"),
        outlet(store_id="store-2", status_aktual="ON"),
        outlet(username="auto7313", nama_portal="Merchant B", store_id="store-3"),
    ], now)

    merchant_a = next(item for item in queue if item.portal_name == "Merchant A")
    assert len(queue) == 2
    assert merchant_a.due_store_ids == ("store-1",)
    assert merchant_a.actionable_count == 1


def test_group_selection_prioritizes_actionable_mismatch_over_heartbeat():
    now = datetime(2026, 8, 31, 12, 30, tzinfo=WIB)
    queue = build_queue([
        outlet(status_aktual="ON", nama_portal="Merchant A"),
        outlet(status_aktual="CLOSED", nama_portal="Merchant B", store_id="store-2"),
    ], now)

    selected = select_next_group(queue, now)
    assert selected is not None
    assert selected.portal_name == "Merchant B"
