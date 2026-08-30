from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Jakarta"
INDONESIA_TIMEZONES = {
    "Asia/Jakarta": "WIB",
    "Asia/Pontianak": "WIB",
    "Asia/Makassar": "WITA",
    "Asia/Ujung_Pandang": "WITA",
    "Asia/Jayapura": "WIT",
}


def normalize_timezone(value) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in INDONESIA_TIMEZONES else DEFAULT_TIMEZONE


def timezone_for(value) -> ZoneInfo:
    return ZoneInfo(normalize_timezone(value))
