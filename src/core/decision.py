"""
core/decision.py
================
Evaluates outlet actions and pause-aware wake-up hints for the automation bot.
"""

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Iterable, Optional, Tuple
from zoneinfo import ZoneInfo

from core.sheets import MerchantOutlet, WEEKDAY_MAP
from core.timezones import DEFAULT_TIMEZONE, timezone_for

ACTION_NO_CHANGE = "NO_CHANGE"
ACTION_OPEN = "ACTION_OPEN"
ACTION_CLOSE = "ACTION_CLOSE"

TARGET_OPEN = "OPEN"
TARGET_CLOSE = "CLOSE"
LOCAL_TZ = ZoneInfo("Asia/Jakarta")
CLOSED_HOUR_VALUES = {"tutup", "closed", "close", "off", "nonaktif"}


@dataclass
class DecisionResult:
    target_state: str        # OPEN / CLOSE
    action: str              # NO_CHANGE / ACTION_OPEN / ACTION_CLOSE
    reason: str              # Explanation of the decision


def _coerce_local_datetime(value: Optional[Any], tz: ZoneInfo = LOCAL_TZ) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw_value = str(value).strip()
        if not raw_value:
            return None
        try:
            dt = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _get_outlet_value(outlet: Any, key: str, default=None):
    if isinstance(outlet, dict):
        return outlet.get(key, default)
    return getattr(outlet, key, default)


def outlet_timezone(outlet: Any) -> ZoneInfo:
    return timezone_for(_get_outlet_value(outlet, "timezone", DEFAULT_TIMEZONE))


def _get_outlet_schedule(outlet: Any) -> dict:
    return _get_outlet_value(outlet, "regular_hours") or _get_outlet_value(outlet, "shopee_regular_hours") or {}


def _iter_schedule_ranges(hours_str) -> Iterable[Tuple[int, int]]:
    if isinstance(hours_str, (list, tuple)):
        for item in hours_str:
            yield from _iter_schedule_ranges(item)
        return

    normalized_hours = (hours_str or "").strip().lower()
    if normalized_hours in CLOSED_HOUR_VALUES or not normalized_hours or "-" not in normalized_hours:
        return

    parts = normalized_hours.split("-")
    if len(parts) != 2:
        return

    try:
        start_h, start_m = map(int, parts[0].strip().split(":"))
        end_h, end_m = map(int, parts[1].strip().split(":"))
    except Exception:
        return

    if (
        start_h not in range(24)
        or end_h not in range(24)
        or start_m not in range(60)
        or end_m not in range(60)
    ):
        return

    yield (start_h * 60 + start_m, end_h * 60 + end_m)


def _format_local_label(value: datetime, timezone: ZoneInfo = LOCAL_TZ) -> str:
    return value.astimezone(timezone).strftime("%d/%m/%Y %H:%M %Z")


def get_active_pause_until(outlet: Any, current_time: Optional[datetime] = None) -> Optional[datetime]:
    local_tz = outlet_timezone(outlet)
    now_local = _coerce_local_datetime(current_time, local_tz) or datetime.now(local_tz)
    pause_until = _coerce_local_datetime(_get_outlet_value(outlet, "pause_until"), local_tz)
    if not pause_until or pause_until <= now_local:
        return None
    return pause_until


def get_next_schedule_start(schedule: dict, now_dt: Optional[datetime] = None, not_after: Optional[datetime] = None, timezone: ZoneInfo = LOCAL_TZ) -> Optional[datetime]:
    now_local = _coerce_local_datetime(now_dt, timezone) or datetime.now(timezone)
    deadline = _coerce_local_datetime(not_after, timezone)
    schedule = schedule or {}

    for day_offset in range(0, 8):
        candidate_date = now_local.date() + timedelta(days=day_offset)
        weekday_name = WEEKDAY_MAP.get(candidate_date.weekday(), "Senin")
        day_intervals = sorted(_iter_schedule_ranges(schedule.get(weekday_name, "")))
        for start_minutes, _end_minutes in day_intervals:
            candidate_dt = datetime(
                candidate_date.year,
                candidate_date.month,
                candidate_date.day,
                tzinfo=timezone,
            ) + timedelta(minutes=start_minutes)
            if candidate_dt <= now_local:
                continue
            if deadline and candidate_dt >= deadline:
                continue
            return candidate_dt
    return None


def get_pause_recheck_delay_seconds(
    outlets: Iterable[Any],
    default_interval_seconds: int,
    now_dt: Optional[datetime] = None,
    effective_now_dt: Optional[datetime] = None,
    buffer_seconds: int = 5,
) -> Tuple[int, str]:
    reference_now = _coerce_local_datetime(now_dt) or datetime.now(LOCAL_TZ)
    effective_now = _coerce_local_datetime(effective_now_dt) or reference_now
    default_delay = max(1, int(default_interval_seconds or 1))
    extra_delay = max(0, int(buffer_seconds or 0))
    nearest_dt = None
    nearest_reason = "default interval"

    for outlet in outlets or []:
        local_tz = outlet_timezone(outlet)
        outlet_now = reference_now.astimezone(local_tz)
        pause_until = get_active_pause_until(outlet, current_time=outlet_now)
        if not pause_until:
            continue

        store_id = _get_outlet_value(outlet, "store_id", "-")
        schedule = _get_outlet_schedule(outlet)
        next_start = get_next_schedule_start(schedule, outlet_now, not_after=pause_until, timezone=local_tz)

        if next_start and (nearest_dt is None or next_start < nearest_dt):
            nearest_dt = next_start
            nearest_reason = (
                f"fast recheck Store {store_id}: sesi reguler berikutnya mulai "
                f"{next_start.astimezone(local_tz).strftime('%H:%M:%S %Z')}"
            )

        if nearest_dt is None or pause_until < nearest_dt:
            nearest_dt = pause_until
            nearest_reason = (
                f"fast recheck Store {store_id}: pause sementara berakhir "
                f"{pause_until.astimezone(local_tz).strftime('%H:%M:%S %Z')}"
            )

    if nearest_dt is None:
        return default_delay, "default interval"

    deadline_dt = nearest_dt + timedelta(seconds=extra_delay)
    delay_seconds = math.ceil((deadline_dt - effective_now).total_seconds())
    if delay_seconds <= 0:
        return 1, f"{nearest_reason}; deadline terlewati saat cycle masih berjalan"
    if delay_seconds >= default_delay:
        return default_delay, "default interval"
    return delay_seconds, nearest_reason


def is_within_operating_hours(hours_str: str, check_time: Optional[time] = None) -> bool:
    """
    Checks if check_time (default: current local time) falls within a string range like "08:00-22:00".
    If hours_str is empty, assumes open 24/7 or valid.
    """
    if isinstance(hours_str, (list, tuple)):
        return bool(hours_str) and any(is_within_operating_hours(interval, check_time) for interval in hours_str)

    normalized_hours = (hours_str or "").strip().lower()
    if normalized_hours in CLOSED_HOUR_VALUES:
        return False
    if not normalized_hours:
        return True
    if "-" not in normalized_hours:
        return False

    parts = normalized_hours.split("-")
    if len(parts) != 2:
        return False

    try:
        start_h, start_m = map(int, parts[0].strip().split(":"))
        end_h, end_m = map(int, parts[1].strip().split(":"))

        start_t = time(start_h, start_m)
        end_t = time(end_h, end_m)

        if check_time is None:
            check_time = datetime.now(LOCAL_TZ).time()

        if start_t <= end_t:
            return start_t <= check_time <= end_t
        else:
            # Overnight shift e.g. 20:00-04:00
            return check_time >= start_t or check_time <= end_t
    except Exception:
        return False


def evaluate_outlet_status(
    outlet: MerchantOutlet,
    current_time: Optional[datetime] = None,
    require_regular_schedule: bool = False,
) -> DecisionResult:
    """
    Evaluates the target status of an outlet based on the PRD priority chain:
    1. Status Penangguhan (Ya/Tidak) -> If "Ya", forced CLOSE.
    2. Status Subscription (Aktif/Kedaluwarsa) -> If not "Aktif", Auto Open disabled -> CLOSE.
    3. Active temporary pause -> Keep outlet closed until pause_until expires.
    4. Operating Hours (Senin-Minggu) -> If outside or unavailable, silently skip.
    5. Vercel Toggle / Status Utama (On/Off) -> Primary Source of Truth.
    """
    local_tz = outlet_timezone(outlet)
    current_time = _coerce_local_datetime(current_time, local_tz) or datetime.now(local_tz)

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
    if outlet.status_langganan.strip().lower() not in ["aktif", "active"]:
        target = TARGET_CLOSE
        reason = "Masa langganan Auto Open telah kedaluwarsa"
        action = ACTION_CLOSE if is_currently_open else ACTION_NO_CHANGE
        return DecisionResult(target_state=target, action=action, reason=reason)

    # 3. Active user/admin pause must survive Shopee's regular schedule breaks.
    active_pause_until = get_active_pause_until(outlet, current_time=current_time)
    if active_pause_until:
        pause_label = _format_local_label(active_pause_until, local_tz)
        if is_currently_open:
            return DecisionResult(
                target_state=TARGET_CLOSE,
                action=ACTION_CLOSE,
                reason=f"Pause aktif sampai {pause_label}; outlet harus tetap tutup",
            )

    # 4. Check Operating Hours for today
    weekday_name = WEEKDAY_MAP.get(current_time.weekday(), "Senin")
    regular_hours = _get_outlet_schedule(outlet)
    today_hours = regular_hours.get(weekday_name, "")

    if active_pause_until:
        pause_label = _format_local_label(active_pause_until, local_tz)
        if require_regular_schedule and not today_hours:
            return DecisionResult(
                target_state=TARGET_CLOSE,
                action=ACTION_NO_CHANGE,
                reason=f"Pause aktif sampai {pause_label}; jadwal reguler Shopee {weekday_name} belum tersedia",
            )
        if not is_within_operating_hours(today_hours, current_time.time()):
            return DecisionResult(
                target_state=TARGET_CLOSE,
                action=ACTION_NO_CHANGE,
                reason=f"Pause aktif sampai {pause_label}; menunggu sesi reguler berikutnya",
            )
        return DecisionResult(
            target_state=TARGET_CLOSE,
            action=ACTION_NO_CHANGE,
            reason=f"Pause aktif sampai {pause_label}; outlet sudah tertutup",
        )

    if require_regular_schedule and not today_hours:
        return DecisionResult(
            target_state=TARGET_CLOSE,
            action=ACTION_NO_CHANGE,
            reason=f"Jadwal reguler Shopee {weekday_name} tidak tersedia",
        )
    
    if not is_within_operating_hours(today_hours, current_time.time()):
        # Shopee owns the CLOSED state outside the regular schedule. Do not
        # translate it into a PAUSE/CLOSE action from the bot.
        target = TARGET_CLOSE
        reason = f"Di luar jam operasional ({weekday_name}: {today_hours or 'Tutup'})"
        action = ACTION_NO_CHANGE
        return DecisionResult(target_state=target, action=action, reason=reason)

    # 5. Vercel Toggle / Status Utama (Source of Truth)
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
