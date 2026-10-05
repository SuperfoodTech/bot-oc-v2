from datetime import datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.decision import (
    evaluate_outlet_status,
    get_active_pause_until,
    get_upcoming_pause_from,
    TARGET_OPEN,
    TARGET_CLOSE,
    ACTION_NO_CHANGE,
    ACTION_CLOSE,
)
from core.sheets import MerchantOutlet
from backend.pause_utils import resolve_pause_range
import backend.main as main_module

WIB = ZoneInfo("Asia/Jakarta")


def test_resolve_pause_range_future_start():
    now_dt = datetime(2026, 10, 5, 9, 0, 0, tzinfo=WIB)
    future_start = "2026-10-05T12:30:00"
    future_end = "2026-10-05T14:30:00"

    pause_until, pause_from, duration_mins, label = resolve_pause_range(
        now_dt,
        duration_type="custom",
        custom_from=future_start,
        custom_until=future_end,
    )

    assert pause_from == datetime(2026, 10, 5, 12, 30, 0, tzinfo=WIB)
    assert pause_until == datetime(2026, 10, 5, 14, 30, 0, tzinfo=WIB)
    assert duration_mins == 120


def test_resolve_pause_range_validation_errors():
    now_dt = datetime(2026, 10, 5, 9, 0, 0, tzinfo=WIB)

    # Past start time (>2 min ago)
    past_start = "2026-10-05T08:00:00"
    future_end = "2026-10-05T14:30:00"
    with pytest.raises(ValueError, match="Waktu mulai tidak boleh waktu lampau"):
        resolve_pause_range(
            now_dt,
            duration_type="custom",
            custom_from=past_start,
            custom_until=future_end,
        )

    # End time before or equal to start time
    start = "2026-10-05T12:00:00"
    invalid_end = "2026-10-05T11:00:00"
    with pytest.raises(ValueError, match="Target waktu berakhir harus lebih besar dari waktu mulai"):
        resolve_pause_range(
            now_dt,
            duration_type="custom",
            custom_from=start,
            custom_until=invalid_end,
        )


def test_decision_logic_with_future_pause():
    regular_hours = {
        "Senin": ["08:00-20:00"],
        "Selasa": ["08:00-20:00"],
        "Rabu": ["08:00-20:00"],
        "Kamis": ["08:00-20:00"],
        "Jumat": ["08:00-20:00"],
        "Sabtu": ["08:00-20:00"],
        "Minggu": ["08:00-20:00"],
    }

    # Store has a scheduled pause starting at 12:30 until 14:30
    outlet = MerchantOutlet(
        store_id="12345",
        status_utama="ON",
        status_aktual="OPEN",
        pause_from="2026-10-05 12:30:00+07:00",
        pause_until="2026-10-05 14:30:00+07:00",
        shopee_regular_hours=regular_hours,
        timezone="Asia/Jakarta",
    )

    # 1. At 09:00 WIB (before pause_from): Store is active and should remain OPEN
    time_0900 = datetime(2026, 10, 5, 9, 0, 0, tzinfo=WIB)
    assert get_active_pause_until(outlet, current_time=time_0900) is None
    assert get_upcoming_pause_from(outlet, current_time=time_0900) is not None

    decision_0900 = evaluate_outlet_status(outlet, current_time=time_0900)
    assert decision_0900.target_state == TARGET_OPEN
    assert decision_0900.action == ACTION_NO_CHANGE

    # 2. At 13:00 WIB (during pause window): Store should be TARGET_CLOSE
    time_1300 = datetime(2026, 10, 5, 13, 0, 0, tzinfo=WIB)
    active_until = get_active_pause_until(outlet, current_time=time_1300)
    assert active_until is not None

    decision_1300 = evaluate_outlet_status(outlet, current_time=time_1300)
    assert decision_1300.target_state == TARGET_CLOSE
    assert decision_1300.action == ACTION_CLOSE

    # 3. At 15:00 WIB (after pause_until): Pause has expired, store resumes normal OPEN
    time_1500 = datetime(2026, 10, 5, 15, 0, 0, tzinfo=WIB)
    assert get_active_pause_until(outlet, current_time=time_1500) is None
    decision_1500 = evaluate_outlet_status(outlet, current_time=time_1500)
    assert decision_1500.target_state == TARGET_OPEN
