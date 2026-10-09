"""Unit tests for On-Demand Schedule Mismatch Resolution in worker.py."""

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.sheets import MerchantOutlet
from core.decision import evaluate_outlet_status, TARGET_OPEN, ACTION_NO_CHANGE, TARGET_CLOSE, ACTION_CLOSE

WIB = ZoneInfo("Asia/Jakarta")


def test_special_hours_open_reverses_decision_and_preserves_store_open():
    """Verify that when live is OPEN, an active special hours overrides close decision."""
    now = datetime(2026, 10, 8, 16, 0, tzinfo=WIB)  # Thursday 16:00
    stale_pause = datetime(2026, 10, 9, 15, 0, tzinfo=WIB)  # Friday 15:00

    # 1. Store without special hours and with stale pause -> decision is ACTION_CLOSE
    outlet = MerchantOutlet(
        username="auto7313",
        nama_portal="Portal Test",
        store_id="21304843",
        nama_panjang_outlet="Roti Bakar 41",
        status_utama="OFF",
        status_aktual="OPEN",
        pause_until=stale_pause.isoformat(),
        regular_hours={"Rabu": ["15:00-22:00"], "Jumat": ["15:00-22:00"]},
        shopee_regular_hours={"Rabu": ["15:00-22:00"], "Jumat": ["15:00-22:00"]},
        shopee_special_hours=[],
        schedule_fetch_status="READY",
        status_langganan="Aktif",
        penangguhan="Tidak",
        timezone="Asia/Jakarta",
    )
    decision = evaluate_outlet_status(outlet, current_time=now, require_regular_schedule=True)
    assert decision.action == ACTION_CLOSE

    # 2. When special hours is fetched on-demand: 15:00 - 22:00 open interval
    special_hours_open = [
        {
            "date_start": 1789318800000,
            "date_end": 2866467599999,
            "date_desc": "Buka Kamis",
            "date_type": 2,
            "intervals": [{"start_relative_sec": 15 * 3600, "end_relative_sec": 22 * 3600}],
        }
    ]
    outlet.shopee_special_hours = special_hours_open

    # Re-evaluate: must become ACTION_NO_CHANGE (TARGET_OPEN)
    new_decision = evaluate_outlet_status(outlet, current_time=now, require_regular_schedule=True)
    assert new_decision.target_state == TARGET_OPEN
    assert new_decision.action == ACTION_NO_CHANGE
    assert "Mengikuti Jadwal Khusus Shopee" in new_decision.reason
