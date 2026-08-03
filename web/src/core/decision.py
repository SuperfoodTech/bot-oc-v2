"""
core/decision.py
================
Evaluates priority logic to determine target store state (OPEN/CLOSE) and required action.
"""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Tuple, Optional
from core.sheets import MerchantOutlet, WEEKDAY_MAP

ACTION_NO_CHANGE = "NO_CHANGE"
ACTION_OPEN = "ACTION_OPEN"
ACTION_CLOSE = "ACTION_CLOSE"

TARGET_OPEN = "OPEN"
TARGET_CLOSE = "CLOSE"


@dataclass
class DecisionResult:
    target_state: str        # OPEN / CLOSE
    action: str              # NO_CHANGE / ACTION_OPEN / ACTION_CLOSE
    reason: str              # Explanation of the decision


def is_within_operating_hours(hours_str: str, check_time: Optional[time] = None) -> bool:
    """
    Checks if check_time (default: current local time) falls within a string range like "08:00-22:00".
    If hours_str is empty, assumes open 24/7 or valid.
    """
    if not hours_str or "-" not in hours_str:
        return True

    parts = hours_str.split("-")
    if len(parts) != 2:
        return True

    try:
        start_h, start_m = map(int, parts[0].strip().split(":"))
        end_h, end_m = map(int, parts[1].strip().split(":"))

        start_t = time(start_h, start_m)
        end_t = time(end_h, end_m)

        if check_time is None:
            check_time = datetime.now().time()

        if start_t <= end_t:
            return start_t <= check_time <= end_t
        else:
            # Overnight shift e.g. 20:00-04:00
            return check_time >= start_t or check_time <= end_t
    except Exception:
        return True


def evaluate_outlet_status(outlet: MerchantOutlet, current_time: Optional[datetime] = None) -> DecisionResult:
    """
    Evaluates the target status of an outlet based on the PRD priority chain:
    1. Status Penangguhan (Ya/Tidak) -> If "Ya", forced CLOSE.
    2. Status Subscription (Aktif/Kedaluwarsa) -> If not "Aktif", Auto Open disabled -> CLOSE.
    3. Operating Hours (Senin-Minggu) -> If outside hours, forced CLOSE.
    4. Vercel Toggle / Status Utama (On/Off) -> Primary Source of Truth.
    """
    if current_time is None:
        current_time = datetime.now()

    # Normalize current actual status from Shopee
    aktual_status_raw = (outlet.status_aktual or "").strip().lower()
    is_currently_open = (aktual_status_raw in ["on", "open", "buka", "2"])

    # 1. Check Penangguhan (Suspension)
    if outlet.penangguhan.strip().lower() == "ya":
        target = TARGET_CLOSE
        reason = f"Outlet ditangguhkan oleh Admin (Alasan: {outlet.alasan_penangguhan or 'N/A'})"
        action = ACTION_CLOSE if is_currently_open else ACTION_NO_CHANGE
        return DecisionResult(target_state=target, action=action, reason=reason)

    # 2. Check Subscription Status
    if outlet.status_langganan.strip().lower() != "aktif":
        target = TARGET_CLOSE
        reason = "Masa langganan Auto Open telah kedaluwarsa"
        action = ACTION_CLOSE if is_currently_open else ACTION_NO_CHANGE
        return DecisionResult(target_state=target, action=action, reason=reason)

    # 3. Check Operating Hours for today
    weekday_name = WEEKDAY_MAP.get(current_time.weekday(), "Senin")
    today_hours = outlet.regular_hours.get(weekday_name, "")
    
    if not is_within_operating_hours(today_hours, current_time.time()):
        target = TARGET_CLOSE
        reason = f"Di luar jam operasional ({weekday_name}: {today_hours})"
        action = ACTION_CLOSE if is_currently_open else ACTION_NO_CHANGE
        return DecisionResult(target_state=target, action=action, reason=reason)

    # 4. Vercel Toggle / Status Utama (Source of Truth)
    status_utama_raw = (outlet.status_utama or "").strip().lower()
    if status_utama_raw in ["on", "open", "buka"]:
        target = TARGET_OPEN
        reason = "Vercel Toggle = ON (Auto Open)"
        action = ACTION_NO_CHANGE if is_currently_open else ACTION_OPEN
    else:
        target = TARGET_CLOSE
        reason = "Vercel Toggle = OFF (Auto Close)"
        action = ACTION_CLOSE if is_currently_open else ACTION_NO_CHANGE

    return DecisionResult(target_state=target, action=action, reason=reason)
