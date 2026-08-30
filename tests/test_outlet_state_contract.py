from datetime import datetime
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.db import derive_outlet_runtime_state


WIB = ZoneInfo("Asia/Jakarta")
ALL_DAY_SCHEDULE = {
    "Senin": ["09:00-21:00"],
    "Selasa": ["09:00-21:00"],
    "Rabu": ["09:00-21:00"],
    "Kamis": ["09:00-21:00"],
    "Jumat": ["09:00-21:00"],
    "Sabtu": ["09:00-21:00"],
    "Minggu": ["09:00-21:00"],
}


def make_store(**overrides):
    store = {
        "vercel_status": "ON",
        "shopee_status": "ON",
        "shopee_regular_hours": ALL_DAY_SCHEDULE,
        "subscription_status": "Aktif",
        "is_suspended": False,
        "suspension_status": "ACTIVE",
        "alasan_penangguhan": "",
        "pause_until": None,
    }
    store.update(overrides)
    return store


def test_pending_pause_keeps_live_open_but_marks_bot_queue():
    derived = derive_outlet_runtime_state(
        make_store(
            vercel_status="OFF",
            shopee_status="ON",
            pause_until="2026-08-30 12:00:00",
        ),
        now_dt=datetime(2026, 8, 30, 10, 0, tzinfo=WIB),
    )

    assert derived["desired_state"] == "PAUSE"
    assert derived["live_state"] == "OPEN"
    assert derived["bot_phase"] == "PENDING_PAUSE"
    assert derived["display_status_label"] == "Sedang Buka • Menunggu bot menutup"
    assert derived["display_toggle_on"] is False
    assert derived["display_toggle_disabled"] is False


def test_pause_state_stays_tutup_sementara_when_live_pause():
    derived = derive_outlet_runtime_state(
        make_store(
            vercel_status="OFF",
            shopee_status="PAUSE",
            pause_until="2026-08-30 12:00:00",
        ),
        now_dt=datetime(2026, 8, 30, 10, 0, tzinfo=WIB),
    )

    assert derived["desired_state"] == "PAUSE"
    assert derived["live_state"] == "PAUSE"
    assert derived["bot_phase"] == "IN_SYNC"
    assert derived["display_status_label"] == "Tutup Sementara"
    assert derived["display_status_tone"] == "paused"


def test_closed_outside_schedule_forces_visual_toggle_off_but_keeps_desired_open():
    derived = derive_outlet_runtime_state(
        make_store(
            vercel_status="ON",
            shopee_status="CLOSED",
        ),
        now_dt=datetime(2026, 8, 30, 23, 0, tzinfo=WIB),
    )

    assert derived["desired_state"] == "OPEN"
    assert derived["live_state"] == "CLOSED"
    assert derived["bot_phase"] == "WAITING_SCHEDULE"
    assert derived["display_status_label"] == "Sedang Tutup • Di luar jadwal"
    assert derived["display_toggle_on"] is False
    assert derived["display_toggle_disabled"] is True
    assert derived["display_toggle_reason"] == "OUTSIDE_SCHEDULE"


def test_closed_during_schedule_waits_for_bot_open_when_toggle_active():
    derived = derive_outlet_runtime_state(
        make_store(
            vercel_status="ON",
            shopee_status="CLOSED",
        ),
        now_dt=datetime(2026, 8, 30, 10, 0, tzinfo=WIB),
    )

    assert derived["desired_state"] == "OPEN"
    assert derived["live_state"] == "CLOSED"
    assert derived["bot_phase"] == "PENDING_OPEN"
    assert derived["display_status_bucket"] == "closed"
    assert derived["display_status_label"] == "Sedang Tutup • Menunggu bot membuka"
    assert "toggle aktif" in derived["display_note"]


def test_manual_off_uses_automation_off_label_even_when_live_pause():
    derived = derive_outlet_runtime_state(
        make_store(
            vercel_status="OFF",
            shopee_status="PAUSE",
            pause_until=None,
        ),
        now_dt=datetime(2026, 8, 30, 10, 0, tzinfo=WIB),
    )

    assert derived["desired_state"] == "MANUAL_OFF"
    assert derived["live_state"] == "PAUSE"
    assert derived["bot_phase"] == "AUTOMATION_OFF"
    assert derived["display_status_label"] == "Sedang Tutup • Otomatisasi nonaktif"


def test_closed_without_schedule_stays_in_checking_state():
    derived = derive_outlet_runtime_state(
        make_store(
            vercel_status="ON",
            shopee_status="CLOSED",
            shopee_regular_hours={},
        ),
        now_dt=datetime(2026, 8, 30, 10, 0, tzinfo=WIB),
    )

    assert derived["bot_phase"] == "SCHEDULE_UNAVAILABLE"
    assert derived["display_status_bucket"] == "closed"
    assert derived["display_status_label"] == "Status sedang dicek bot"
    assert derived["display_toggle_disabled"] is True
    assert derived["display_toggle_reason"] == "SCHEDULE_UNAVAILABLE"


def test_unknown_live_with_active_toggle_counts_as_open_bucket():
    derived = derive_outlet_runtime_state(
        make_store(
            vercel_status="ON",
            shopee_status="UNKNOWN",
        ),
        now_dt=datetime(2026, 8, 30, 10, 0, tzinfo=WIB),
    )

    assert derived["bot_phase"] == "STATUS_UNKNOWN"
    assert derived["display_toggle_on"] is True
    assert derived["display_status_bucket"] == "open"
    assert derived["display_status_label"] == "Status sedang dicek bot"
