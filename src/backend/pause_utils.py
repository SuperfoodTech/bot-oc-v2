from datetime import datetime, time, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo


WIB = ZoneInfo("Asia/Jakarta")
FULL_DAY_MINUTES = 24 * 60


def _as_local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=WIB)
    return value.astimezone(WIB)


def _iter_schedule_ranges(hours: object) -> Iterable[tuple[int, int]]:
    values = hours if isinstance(hours, (list, tuple)) else [hours]
    for value in values:
        raw = str(value or "").strip()
        if not raw or "-" not in raw:
            continue
        start_raw, end_raw = (part.strip() for part in raw.split("-", 1))
        try:
            start_hour, start_minute = (int(part) for part in start_raw.split(":", 1))
            end_hour, end_minute = (int(part) for part in end_raw.split(":", 1))
        except (ValueError, TypeError):
            continue
        if not (0 <= start_hour < 24 and 0 <= end_hour < 24 and 0 <= start_minute < 60 and 0 <= end_minute < 60):
            continue
        yield start_hour * 60 + start_minute, end_hour * 60 + end_minute


def next_operational_start(schedule: Optional[dict], now_dt: datetime) -> Optional[datetime]:
    """Return the first valid operating-session start after today's date."""
    if not schedule:
        return None

    now_local = _as_local_datetime(now_dt)
    for day_offset in range(1, 8):
        candidate_date = now_local.date() + timedelta(days=day_offset)
        # Python weekday: Monday=0, Sunday=6. The stored schedule uses names.
        day_name = (
            "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"
        )[candidate_date.weekday()]
        starts = sorted(start for start, _end in _iter_schedule_ranges(schedule.get(day_name)))
        if starts:
            start_minutes = starts[0]
            return datetime.combine(candidate_date, time.min, tzinfo=WIB) + timedelta(minutes=start_minutes)
    return None


def parse_pause_until(value: str, tz: ZoneInfo = WIB) -> datetime:
    pause_until_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if pause_until_dt.tzinfo is not None:
        return pause_until_dt.astimezone(tz)
    return pause_until_dt.replace(tzinfo=tz)


def resolve_pause_window(
    now_dt: datetime,
    duration_type: str,
    *,
    schedule: Optional[dict] = None,
    custom_until: Optional[str] = None,
    custom_minutes: Optional[int] = None,
    allow_default: bool = True,
) -> tuple[datetime, int, str]:
    now_dt = _as_local_datetime(now_dt)
    dtype = (duration_type or "").strip().lower()

    if dtype in ("30", "30_min", "30min"):
        duration_mins = 30
        pause_until_dt = now_dt + timedelta(minutes=duration_mins)
        return pause_until_dt, duration_mins, "30 Menit"

    if dtype in ("60", "60_min", "60min"):
        duration_mins = 60
        pause_until_dt = now_dt + timedelta(minutes=duration_mins)
        return pause_until_dt, duration_mins, "60 Menit"

    if dtype in ("rest_of_day", "sepanjang_hari", "today"):
        pause_until_dt = next_operational_start(schedule, now_dt)
        if pause_until_dt is None:
            raise ValueError("Jadwal operasional hari berikutnya belum tersedia.")
        duration_mins = max(1, int((pause_until_dt - now_dt).total_seconds() // 60))
        return pause_until_dt, duration_mins, "Sepanjang Hari"

    if dtype in ("custom", "waktu_lain"):
        if custom_until:
            try:
                pause_until_dt = parse_pause_until(custom_until)
            except ValueError as exc:
                raise ValueError("Target waktu penutupan tidak valid.") from exc
            duration_mins = int((pause_until_dt - now_dt).total_seconds() // 60)
            if duration_mins <= 0:
                raise ValueError("Target waktu harus lebih besar dari waktu sekarang.")
            return pause_until_dt, duration_mins, f"Sampai {pause_until_dt.strftime('%d/%m/%Y %H:%M')}"

        duration_mins = custom_minutes or 0
        if duration_mins <= 0:
            raise ValueError("Target waktu penutupan wajib diisi.")
        pause_until_dt = now_dt + timedelta(minutes=duration_mins)
        return pause_until_dt, duration_mins, f"Sampai {pause_until_dt.strftime('%d/%m/%Y %H:%M')}"

    if allow_default:
        pause_until_dt = next_operational_start(schedule, now_dt)
        if pause_until_dt is None:
            raise ValueError("Jadwal operasional hari berikutnya belum tersedia.")
        duration_mins = max(1, int((pause_until_dt - now_dt).total_seconds() // 60))
        return pause_until_dt, duration_mins, "Sepanjang Hari"

    raise ValueError("Durasi pause wajib dipilih.")
