from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.decision import (
    ACTION_CLOSE,
    ACTION_NO_CHANGE,
    ACTION_OPEN,
    TARGET_CLOSE,
    TARGET_OPEN,
    evaluate_outlet_status,
    get_active_special_hours,
    is_within_special_hours_intervals,
)
from core.sheets import MerchantOutlet
from backend.db import derive_outlet_runtime_state

WIB = ZoneInfo("Asia/Jakarta")


class TestSpecialHoursScheduleGate(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 17, 13, 0, 0, tzinfo=WIB)
        # 14 Sept 2026 00:00 WIB -> 31 Oct 2060 23:59 WIB
        self.special_closed = [
            {
                "date_start": 1789318800000,
                "date_end": 2866467599999,
                "date_desc": "Libur Panjang",
                "date_type": 1,
                "intervals": [{"start_relative_sec": 0, "end_relative_sec": 0}],
            }
        ]
        self.regular_hours = {
            "Senin": ["08:00-17:00"],
            "Selasa": ["08:00-17:00"],
            "Rabu": ["08:00-17:00"],
            "Kamis": ["08:00-17:00"],
            "Jumat": ["08:00-17:00"],
            "Sabtu": ["08:00-17:00"],
            "Minggu": ["08:00-17:00"],
        }

    def test_special_hours_active_closed_locks_toggle_and_bot_decision(self):
        outlet = MerchantOutlet(
            store_id="21901629",
            nama_panjang_outlet="Rawon dan Lontong Sayur, Lokarasa",
            status_utama="ON",
            status_aktual="CLOSED",
            regular_hours=self.regular_hours,
            shopee_regular_hours=self.regular_hours,
            shopee_special_hours=self.special_closed,
            timezone="Asia/Jakarta",
        )

        decision = evaluate_outlet_status(outlet, current_time=self.now)
        self.assertEqual(decision.target_state, TARGET_CLOSE)
        self.assertEqual(decision.action, ACTION_NO_CHANGE)
        self.assertIn("Tutup berdasarkan Jadwal Khusus Shopee", decision.reason)

        # If currently open in Shopee, bot must trigger ACTION_CLOSE
        outlet.status_aktual = "OPEN"
        decision_open = evaluate_outlet_status(outlet, current_time=self.now)
        self.assertEqual(decision_open.target_state, TARGET_CLOSE)
        self.assertEqual(decision_open.action, ACTION_CLOSE)

        # Test backend state derivation
        store_dict = {
            "store_id": "21901629",
            "store_name": "Rawon dan Lontong Sayur, Lokarasa",
            "vercel_status": "ON",
            "shopee_status": "CLOSED",
            "shopee_regular_hours": self.regular_hours,
            "shopee_special_hours": self.special_closed,
            "timezone": "Asia/Jakarta",
            "schedule_fetch_status": "READY",
        }
        runtime_state = derive_outlet_runtime_state(store_dict, now_dt=self.now)
        self.assertFalse(runtime_state["display_toggle_on"])
        self.assertTrue(runtime_state["display_toggle_disabled"])
        self.assertEqual(runtime_state["display_toggle_reason"], "SPECIAL_HOURS")
        self.assertFalse(runtime_state["within_operating_schedule"])
        self.assertEqual(runtime_state["bot_phase"], "WAITING_SCHEDULE")
        self.assertEqual(runtime_state["display_status_label"], "Sedang Tutup • Jadwal Khusus")

    def test_special_hours_custom_intervals_open_when_within_time(self):
        # Special hours 10:00 - 14:00 (36000s - 50400s)
        special_custom = [
            {
                "date_start": 1789318800000,
                "date_end": 2866467599999,
                "date_desc": "Buka Siang Saja",
                "date_type": 2,
                "intervals": [{"start_relative_sec": 36000, "end_relative_sec": 50400}],
            }
        ]
        outlet = MerchantOutlet(
            store_id="21901629",
            status_utama="ON",
            status_aktual="CLOSED",
            shopee_regular_hours=self.regular_hours,
            shopee_special_hours=special_custom,
            timezone="Asia/Jakarta",
        )
        # At 13:00 WIB (within 10:00 - 14:00) -> Open
        decision = evaluate_outlet_status(outlet, current_time=self.now)
        self.assertEqual(decision.target_state, TARGET_OPEN)
        self.assertEqual(decision.action, ACTION_OPEN)

        # At 15:00 WIB (outside 10:00 - 14:00) -> Closed
        time_15 = datetime(2026, 9, 17, 15, 0, 0, tzinfo=WIB)
        decision_15 = evaluate_outlet_status(outlet, current_time=time_15)
        self.assertEqual(decision_15.target_state, TARGET_CLOSE)
        self.assertEqual(decision_15.action, ACTION_NO_CHANGE)

    def test_special_hours_fallback_to_regular_when_not_active(self):
        # Special hours in past (ended 2026-09-10)
        past_special = [
            {
                "date_start": 1788000000000,
                "date_end": 1789000000000,
                "date_desc": "Libur Kemarin",
                "date_type": 1,
                "intervals": [{"start_relative_sec": 0, "end_relative_sec": 0}],
            }
        ]
        outlet = MerchantOutlet(
            store_id="21901629",
            status_utama="ON",
            status_aktual="CLOSED",
            shopee_regular_hours=self.regular_hours,
            shopee_special_hours=past_special,
            timezone="Asia/Jakarta",
        )
        # At 13:00 WIB on Thursday (within regular 08:00 - 17:00) -> Opens by regular schedule
        decision = evaluate_outlet_status(outlet, current_time=self.now)
        self.assertEqual(decision.target_state, TARGET_OPEN)
        self.assertEqual(decision.action, ACTION_OPEN)


if __name__ == "__main__":
    unittest.main()
