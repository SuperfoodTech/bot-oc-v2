import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.pause_utils import resolve_pause_window


class PauseUtilsTests(unittest.TestCase):
    def test_rest_of_day_ends_at_first_session_on_next_day(self):
        now_dt = datetime(2026, 8, 31, 21, 0, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        schedule = {"Senin": ["07:00-22:00"], "Selasa": ["07:00-22:00"]}

        pause_until_dt, duration_mins, label = resolve_pause_window(
            now_dt, "rest_of_day", schedule=schedule
        )

        expected = datetime(2026, 9, 1, 7, 0, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        self.assertEqual(pause_until_dt, expected)
        self.assertEqual(duration_mins, 600)
        self.assertEqual(label, "Sepanjang Hari")

    def test_rest_of_day_skips_empty_next_day_and_uses_first_session(self):
        now_dt = datetime(2026, 8, 31, 9, 0, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        schedule = {"Senin": ["07:00-22:00"], "Rabu": ["10:00-12:00", "15:00-18:00"]}

        pause_until_dt, duration_mins, label = resolve_pause_window(
            now_dt, "today", schedule=schedule
        )

        expected = datetime(2026, 9, 2, 10, 0, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        self.assertEqual(pause_until_dt, expected)
        self.assertEqual(duration_mins, 2940)
        self.assertEqual(label, "Sepanjang Hari")

    def test_rest_of_day_works_with_multi_schedule_next_day(self):
        now_dt = datetime(2026, 8, 30, 21, 0, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        schedule = {"Minggu": ["10:00-15:15", "15:20-21:00"], "Senin": ["08:00-12:00"]}

        pause_until_dt, _duration_mins, _label = resolve_pause_window(
            now_dt, "rest_of_day", schedule=schedule
        )

        self.assertEqual(
            pause_until_dt,
            datetime(2026, 8, 31, 8, 0, 0, tzinfo=ZoneInfo("Asia/Jakarta")),
        )


if __name__ == "__main__":
    unittest.main()
