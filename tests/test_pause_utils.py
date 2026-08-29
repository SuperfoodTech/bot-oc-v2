import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.pause_utils import FULL_DAY_MINUTES, resolve_pause_window


class PauseUtilsTests(unittest.TestCase):
    def test_rest_of_day_means_true_24_hour_pause(self):
        now_dt = datetime(2026, 8, 29, 10, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))

        pause_until_dt, duration_mins, label = resolve_pause_window(now_dt, "rest_of_day")

        self.assertEqual(duration_mins, FULL_DAY_MINUTES)
        self.assertEqual(pause_until_dt, now_dt + timedelta(minutes=FULL_DAY_MINUTES))
        self.assertEqual(label, "Sepanjang Hari (24 Jam)")

    def test_today_alias_uses_same_24_hour_window(self):
        now_dt = datetime(2026, 8, 29, 22, 5, 0, tzinfo=ZoneInfo("Asia/Jakarta"))

        pause_until_dt, duration_mins, label = resolve_pause_window(now_dt, "today")

        self.assertEqual(duration_mins, FULL_DAY_MINUTES)
        self.assertEqual(pause_until_dt, now_dt + timedelta(minutes=FULL_DAY_MINUTES))
        self.assertEqual(label, "Sepanjang Hari (24 Jam)")


if __name__ == "__main__":
    unittest.main()
