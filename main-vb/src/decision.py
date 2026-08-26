"""VB decision entry point.

The patrol worker remains byte-for-byte identical to bot-OC. VB has one
intentional business-rule difference: service expiry and suspension are not
inputs to the Virtual Brand toggle. After the regular-hours gate, the brand
toggle is the sole target-state source.
"""

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from core.decision import *  # noqa: F401,F403
from core.decision import DecisionResult


def evaluate_outlet_status(
    outlet: MerchantOutlet,
    current_time: Optional[datetime] = None,
    require_regular_schedule: bool = False,
) -> DecisionResult:
    """Evaluate VB by schedule plus the Virtual Brand toggle only."""
    if current_time is None:
        current_time = datetime.now(ZoneInfo("Asia/Jakarta"))

    actual = (outlet.status_aktual or "").strip().lower()
    is_currently_open = actual in {"on", "open", "buka", "2"}
    weekday_name = WEEKDAY_MAP.get(current_time.weekday(), "Senin")
    today_hours = (outlet.regular_hours or {}).get(weekday_name, "")

    if require_regular_schedule and not today_hours:
        return DecisionResult(
            target_state=TARGET_CLOSE,
            action=ACTION_NO_CHANGE,
            reason=f"Jadwal reguler Shopee {weekday_name} tidak tersedia",
        )

    if not is_within_operating_hours(today_hours, current_time.time()):
        return DecisionResult(
            target_state=TARGET_CLOSE,
            action=ACTION_NO_CHANGE,
            reason=f"Di luar jam operasional ({weekday_name}: {today_hours or 'Tutup'})",
        )

    if actual in {"closed", "close"}:
        return DecisionResult(
            target_state=TARGET_CLOSE,
            action=ACTION_NO_CHANGE,
            reason="Shopee CLOSED di dalam jam reguler; dianggap jadwal khusus",
        )

    toggle = (outlet.status_utama or "OFF").strip().lower()
    if toggle in {"on", "open", "buka"}:
        return DecisionResult(
            target_state=TARGET_OPEN,
            action=ACTION_NO_CHANGE if is_currently_open else ACTION_OPEN,
            reason="Virtual Brand Toggle = ON",
        )

    return DecisionResult(
        target_state=TARGET_CLOSE,
        action=ACTION_CLOSE if is_currently_open else ACTION_NO_CHANGE,
        reason="Virtual Brand Toggle = OFF",
    )
