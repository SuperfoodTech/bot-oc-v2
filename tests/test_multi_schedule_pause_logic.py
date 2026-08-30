from datetime import datetime
import sys
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.decision import (
    ACTION_CLOSE,
    ACTION_OPEN,
    ACTION_NO_CHANGE,
    TARGET_CLOSE,
    TARGET_OPEN,
    evaluate_outlet_status,
    get_next_schedule_start,
    get_pause_recheck_delay_seconds,
)
from core.sheets import MerchantOutlet


WIB = ZoneInfo("Asia/Jakarta")
MULTI_SCHEDULE = {
    "Sabtu": ["12:00-13:40", "14:00-15:00"],
}


def make_outlet(**overrides) -> MerchantOutlet:
    outlet = MerchantOutlet(
        store_id="12345",
        nama_panjang_outlet="Outlet Multi Schedule",
        status_utama="Off",
        status_aktual="CLOSED",
        status_langganan="Aktif",
        penangguhan="Tidak",
        pause_until="2026-08-29 14:30:00",
        regular_hours=MULTI_SCHEDULE,
        shopee_regular_hours=MULTI_SCHEDULE,
    )
    for key, value in overrides.items():
        setattr(outlet, key, value)
    return outlet


def test_active_pause_recloses_store_when_second_schedule_starts():
    outlet = make_outlet(status_aktual="OPEN")

    decision = evaluate_outlet_status(
        outlet,
        current_time=datetime(2026, 8, 29, 14, 5, tzinfo=WIB),
        require_regular_schedule=True,
    )

    assert decision.target_state == TARGET_CLOSE
    assert decision.action == ACTION_CLOSE
    assert "Pause aktif sampai" in decision.reason
    assert "outlet harus tetap tutup" in decision.reason


def test_active_pause_during_break_waits_for_next_regular_session():
    outlet = make_outlet(status_aktual="CLOSED")

    decision = evaluate_outlet_status(
        outlet,
        current_time=datetime(2026, 8, 29, 13, 45, tzinfo=WIB),
        require_regular_schedule=True,
    )

    assert decision.target_state == TARGET_CLOSE
    assert decision.action == ACTION_NO_CHANGE
    assert "menunggu sesi reguler berikutnya" in decision.reason


def test_next_schedule_start_finds_second_interval_before_pause_ends():
    next_start = get_next_schedule_start(
        MULTI_SCHEDULE,
        now_dt=datetime(2026, 8, 29, 13, 45, tzinfo=WIB),
        not_after=datetime(2026, 8, 29, 14, 30, tzinfo=WIB),
    )

    assert next_start == datetime(2026, 8, 29, 14, 0, tzinfo=WIB)


def test_pause_recheck_uses_nearest_schedule_boundary_before_default_interval():
    outlet = make_outlet()

    delay_seconds, reason = get_pause_recheck_delay_seconds(
        [outlet],
        default_interval_seconds=3600,
        now_dt=datetime(2026, 8, 29, 13, 45, tzinfo=WIB),
    )

    assert delay_seconds == 905
    assert "14:00:00 WIB" in reason


def test_pause_recheck_turns_immediate_when_boundary_passes_mid_cycle():
    outlet = make_outlet()

    delay_seconds, reason = get_pause_recheck_delay_seconds(
        [outlet],
        default_interval_seconds=3600,
        now_dt=datetime(2026, 8, 29, 13, 45, tzinfo=WIB),
        effective_now_dt=datetime(2026, 8, 29, 14, 1, tzinfo=WIB),
    )

    assert delay_seconds == 1
    assert "deadline terlewati saat cycle masih berjalan" in reason


def test_toggle_on_reopens_closed_store_during_regular_hours():
    outlet = make_outlet(
        status_utama="On",
        status_aktual="CLOSED",
        pause_until="",
    )

    decision = evaluate_outlet_status(
        outlet,
        current_time=datetime(2026, 8, 29, 12, 30, tzinfo=WIB),
        require_regular_schedule=True,
    )

    assert decision.target_state == TARGET_OPEN
    assert decision.action == ACTION_OPEN
    assert "Vercel Toggle = ON" in decision.reason
