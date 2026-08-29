from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo


WIB = ZoneInfo("Asia/Jakarta")
FULL_DAY_MINUTES = 24 * 60


def parse_pause_until(value: str, tz: ZoneInfo = WIB) -> datetime:
    pause_until_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if pause_until_dt.tzinfo is not None:
        return pause_until_dt.astimezone(tz)
    return pause_until_dt.replace(tzinfo=tz)


def resolve_pause_window(
    now_dt: datetime,
    duration_type: str,
    *,
    custom_until: Optional[str] = None,
    custom_minutes: Optional[int] = None,
    allow_default: bool = True,
) -> tuple[datetime, int, str]:
    dtype = (duration_type or "").strip().lower()

    if dtype in ("30", "30_min", "30min"):
        duration_mins = 30
        pause_until_dt = now_dt + timedelta(minutes=duration_mins)
        return pause_until_dt, duration_mins, "30 Menit"

    if dtype in ("60", "60_min", "60min"):
        duration_mins = 60
        pause_until_dt = now_dt + timedelta(minutes=duration_mins)
        return pause_until_dt, duration_mins, "60 Menit"

    # Keep the legacy token `rest_of_day`, but treat it as a true 24-hour pause.
    if dtype in ("rest_of_day", "sepanjang_hari", "today"):
        duration_mins = FULL_DAY_MINUTES
        pause_until_dt = now_dt + timedelta(minutes=duration_mins)
        return pause_until_dt, duration_mins, "Sepanjang Hari (24 Jam)"

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
        duration_mins = FULL_DAY_MINUTES
        pause_until_dt = now_dt + timedelta(minutes=duration_mins)
        return pause_until_dt, duration_mins, "Default (24 Jam)"

    raise ValueError("Durasi pause wajib dipilih.")
