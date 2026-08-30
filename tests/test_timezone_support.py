from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.pause_utils import resolve_pause_window
from core.decision import ACTION_OPEN, evaluate_outlet_status
from core.sheets import MerchantOutlet
from core.timezones import DEFAULT_TIMEZONE, normalize_timezone


def test_rest_of_day_uses_wita_local_calendar_and_next_session():
    now = datetime(2026, 8, 31, 21, 0, tzinfo=ZoneInfo("Asia/Makassar"))
    schedule = {"Senin": ["07:00-22:00"], "Selasa": ["07:00-22:00"]}

    pause_until, duration_mins, _label = resolve_pause_window(
        now, "rest_of_day", schedule=schedule, timezone="Asia/Makassar"
    )

    assert pause_until == datetime(2026, 9, 1, 7, 0, tzinfo=ZoneInfo("Asia/Makassar"))
    assert duration_mins == 600


def test_rest_of_day_uses_wit_local_calendar():
    now = datetime(2026, 8, 31, 21, 0, tzinfo=ZoneInfo("Asia/Jayapura"))
    schedule = {"Senin": ["07:00-22:00"], "Selasa": ["10:00-12:00"]}

    pause_until, _duration_mins, _label = resolve_pause_window(
        now, "sepanjang_hari", schedule=schedule, timezone="Asia/Jayapura"
    )

    assert pause_until == datetime(2026, 9, 1, 10, 0, tzinfo=ZoneInfo("Asia/Jayapura"))


def test_custom_naive_pause_time_is_interpreted_in_outlet_timezone():
    now = datetime(2026, 8, 31, 21, 0, tzinfo=ZoneInfo("Asia/Makassar"))

    pause_until, _duration_mins, _label = resolve_pause_window(
        now,
        "custom",
        timezone="Asia/Makassar",
        custom_until="2026-08-31T22:00",
    )

    assert pause_until == datetime(2026, 8, 31, 22, 0, tzinfo=ZoneInfo("Asia/Makassar"))


def test_schedule_evaluation_uses_outlet_timezone_not_server_timezone():
    outlet = MerchantOutlet(
        store_id="makassar-1",
        status_utama="On",
        status_aktual="CLOSED",
        status_langganan="Aktif",
        penangguhan="Tidak",
        regular_hours={"Senin": ["10:00-12:00"]},
        shopee_regular_hours={"Senin": ["10:00-12:00"]},
        timezone="Asia/Makassar",
    )

    decision = evaluate_outlet_status(
        outlet,
        current_time=datetime(2026, 8, 31, 2, 0, tzinfo=ZoneInfo("UTC")),
        require_regular_schedule=True,
    )

    assert decision.action == ACTION_OPEN


def test_unknown_timezone_falls_back_to_wib():
    assert normalize_timezone("Mars/Base") == DEFAULT_TIMEZONE
