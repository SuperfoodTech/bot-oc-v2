"""PostgreSQL operational store for the monolith dashboard and bot."""

import os
import re
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from zoneinfo import ZoneInfo

from core.timezones import normalize_timezone, timezone_for

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster")
BOT_USERNAME = os.getenv("SHOPEE_BOT_USERNAME", "auto7313")
BOT_PASSWORD = os.getenv("SHOPEE_BOT_PASSWORD", "Auto@7313")
WIB = ZoneInfo("Asia/Jakarta")
WEEKDAY_NAMES = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}
SCHEDULE_DAY_NAMES = {
    # Shopee regular-hours API uses 1=Sunday through 7=Saturday.
    1: "Minggu",
    2: "Senin",
    3: "Selasa",
    4: "Rabu",
    5: "Kamis",
    6: "Jumat",
    7: "Sabtu",
}
SCHEDULE_DAY_ORDER = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
SCHEDULE_RANGE_RE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")
SCHEDULE_FETCH_NOT_FETCHED_YET = "NOT_FETCHED_YET"
SCHEDULE_FETCH_RETRYING = "FETCH_RETRYING"
SCHEDULE_FETCH_EMPTY = "FETCHED_EMPTY"
SCHEDULE_FETCH_READY = "READY"
SCHEDULE_FETCH_STATUS_VALUES = {
    SCHEDULE_FETCH_NOT_FETCHED_YET,
    SCHEDULE_FETCH_RETRYING,
    SCHEDULE_FETCH_EMPTY,
    SCHEDULE_FETCH_READY,
}


def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db() -> None:
    base_dir = Path(__file__).resolve().parents[2] / "database" / "migrations"
    schema_path = base_dir / "001_initial_schema.sql"
    migration2_path = base_dir / "002_separate_merchant_outlet.sql"
    migration3_path = base_dir / "003_add_google_auth.sql"
    migration4_path = base_dir / "004_virtual_brand.sql"
    with get_db_connection() as conn:
        conn.execute(schema_path.read_text(encoding="utf-8"))
        if migration2_path.exists():
            conn.execute(migration2_path.read_text(encoding="utf-8"))
        if migration3_path.exists():
            conn.execute(migration3_path.read_text(encoding="utf-8"))
        if migration4_path.exists():
            conn.execute(migration4_path.read_text(encoding="utf-8"))
        migration5_path = base_dir / "005_remove_ownership_type.sql"
        if migration5_path.exists():
            conn.execute(migration5_path.read_text(encoding="utf-8"))
        migration6_path = base_dir / "006_log_overview_and_errors.sql"
        if migration6_path.exists():
            conn.execute(migration6_path.read_text(encoding="utf-8"))
        migration7_path = base_dir / "007_shopee_regular_hours.sql"
        if migration7_path.exists():
            conn.execute(migration7_path.read_text(encoding="utf-8"))
        migration8_path = base_dir / "008_vb_brand_pause_until.sql"
        if migration8_path.exists():
            conn.execute(migration8_path.read_text(encoding="utf-8"))
        migration9_path = base_dir / "009_expand_shopee_actual_status.sql"
        if migration9_path.exists():
            conn.execute(migration9_path.read_text(encoding="utf-8"))
        migration10_path = base_dir / "010_fix_shopee_weekday_mapping.sql"
        if migration10_path.exists():
            conn.execute(migration10_path.read_text(encoding="utf-8"))
        migration11_path = base_dir / "011_pause_mode.sql"
        if migration11_path.exists():
            conn.execute(migration11_path.read_text(encoding="utf-8"))
        migration12_path = base_dir / "012_outlet_timezone.sql"
        if migration12_path.exists():
            conn.execute(migration12_path.read_text(encoding="utf-8"))
        migration13_path = base_dir / "013_schedule_fetch_status.sql"
        if migration13_path.exists():
            conn.execute(migration13_path.read_text(encoding="utf-8"))
        # Upgrade databases created by the earlier draft without deleting data.
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS password_plain text")
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS link_slug varchar(255)")
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS dashboard_url text")
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS role varchar(20) DEFAULT 'MERCHANT'")
        # Keep passwords imported from Google Sheet. Only initialize legacy or
        # newly-added merchant accounts when the password is actually empty.
        conn.execute("UPDATE dashboard_accounts SET password_plain='Master@00@' WHERE (role='MERCHANT' OR role IS NULL) AND (password_plain IS NULL OR BTRIM(password_plain)='')")
        conn.execute("ALTER TABLE dashboard_accounts DROP COLUMN IF EXISTS password_hash")
        conn.execute("ALTER TABLE shopee_accounts ADD COLUMN IF NOT EXISTS password_plain text")
        conn.execute("ALTER TABLE shopee_accounts ADD COLUMN IF NOT EXISTS merchant_id_external varchar(100) DEFAULT ''")
        conn.execute("UPDATE shopee_accounts SET password_plain=COALESCE(password_plain, '') WHERE password_plain IS NULL")
        conn.execute("ALTER TABLE outlets DROP COLUMN IF EXISTS short_name")
        conn.execute("CREATE TABLE IF NOT EXISTS system_settings (key varchar(100) PRIMARY KEY, value text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")
        conn.execute(
            "INSERT INTO dashboard_accounts (username,password_plain,role,is_active) VALUES (%s,%s,'ADMIN',true) ON CONFLICT (username) DO NOTHING",
            (admin_username, admin_password),
        )
        conn.execute("INSERT INTO bot_accounts (username,password_plain,name) VALUES (%s,%s,%s) ON CONFLICT (username) DO UPDATE SET password_plain=EXCLUDED.password_plain,updated_at=now()", (BOT_USERNAME, BOT_PASSWORD, "Bot Satpam Utama"))


def _coerce_pause_until(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        pause_until_dt = value
    else:
        raw_value = str(value).strip()
        if not raw_value:
            return None
        try:
            pause_until_dt = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if pause_until_dt.tzinfo is None:
        return pause_until_dt.replace(tzinfo=WIB)
    return pause_until_dt.astimezone(WIB)


def _empty_schedule_map() -> Dict[str, List[str]]:
    return {day_name: [] for day_name in SCHEDULE_DAY_ORDER}


def _normalize_schedule_interval(value) -> Optional[str]:
    if isinstance(value, dict):
        try:
            start = max(0, int(value.get("start_relative_sec", 0)))
            end = max(0, int(value.get("end_relative_sec", 0)))
        except (TypeError, ValueError):
            return None
        if end <= start:
            return None
        return f"{start // 3600:02d}:{(start % 3600) // 60:02d}-{end // 3600:02d}:{(end % 3600) // 60:02d}"

    raw_value = str(value or "").strip().replace(".", ":")
    if not raw_value or raw_value.lower() in {"tutup", "closed", "close", "off", "nonaktif"}:
        return None
    match = SCHEDULE_RANGE_RE.match(raw_value)
    if not match:
        return None
    start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
    if (
        start_hour not in range(24)
        or end_hour not in range(24)
        or start_minute not in range(60)
        or end_minute not in range(60)
    ):
        return None
    return f"{start_hour:02d}:{start_minute:02d}-{end_hour:02d}:{end_minute:02d}"


def _append_schedule_intervals(target: Dict[str, List[str]], day_name: str, raw_value) -> None:
    if day_name not in target:
        return
    if isinstance(raw_value, (list, tuple)):
        for item in raw_value:
            _append_schedule_intervals(target, day_name, item)
        return
    normalized = _normalize_schedule_interval(raw_value)
    if normalized and normalized not in target[day_name]:
        target[day_name].append(normalized)


def normalize_shopee_regular_hours(raw_schedule) -> Dict[str, List[str]]:
    schedule = raw_schedule
    if isinstance(schedule, str):
        stripped = schedule.strip()
        if not stripped:
            return {}
        try:
            schedule = json.loads(stripped)
        except json.JSONDecodeError:
            return {}

    normalized = _empty_schedule_map()

    if isinstance(schedule, dict) and isinstance(schedule.get("regular_hours"), list):
        schedule = schedule.get("regular_hours") or []

    if isinstance(schedule, list):
        for day in schedule:
            if not isinstance(day, dict):
                continue
            try:
                day_name = SCHEDULE_DAY_NAMES.get(int(day.get("weekday", 0)))
            except (TypeError, ValueError):
                day_name = None
            if not day_name or not day.get("config_enabled"):
                continue
            _append_schedule_intervals(normalized, day_name, day.get("intervals") or [])
        return {key: value for key, value in normalized.items() if value}

    if isinstance(schedule, dict):
        for day_name in SCHEDULE_DAY_ORDER:
            _append_schedule_intervals(normalized, day_name, schedule.get(day_name))
        return {key: value for key, value in normalized.items() if value}

    return {}


def has_usable_shopee_schedule(raw_schedule) -> bool:
    schedule = normalize_shopee_regular_hours(raw_schedule)
    return any(schedule.values())


def _normalized_schedule_has_intervals(schedule: Optional[Dict[str, List[str]]]) -> bool:
    return any((schedule or {}).values())


def _clean_schedule_fetch_error(value) -> Optional[str]:
    raw_value = str(value or "").strip()
    return raw_value or None


def _derive_schedule_fetch_status(
    store: Dict[str, Any],
    *,
    schedule_available: bool,
) -> str:
    if schedule_available:
        return SCHEDULE_FETCH_READY

    normalized = str(store.get("schedule_fetch_status") or "").strip().upper()
    attempted_at = store.get("schedule_fetch_attempted_at")
    succeeded_at = store.get("schedule_fetch_succeeded_at")
    error_message = _clean_schedule_fetch_error(store.get("schedule_fetch_error"))

    if normalized in {
        SCHEDULE_FETCH_NOT_FETCHED_YET,
        SCHEDULE_FETCH_RETRYING,
        SCHEDULE_FETCH_EMPTY,
    }:
        return normalized
    if succeeded_at and not error_message:
        return SCHEDULE_FETCH_EMPTY
    if attempted_at or error_message:
        return SCHEDULE_FETCH_RETRYING
    return SCHEDULE_FETCH_NOT_FETCHED_YET


def _parse_schedule_range(range_text: str) -> Optional[Tuple[int, int]]:
    match = SCHEDULE_RANGE_RE.match(str(range_text or "").strip())
    if not match:
        return None
    start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
    return (start_hour * 60 + start_minute, end_hour * 60 + end_minute)


def _is_within_normalized_schedule(schedule: Dict[str, List[str]], now_dt: datetime) -> bool:
    day_name = WEEKDAY_NAMES.get(now_dt.weekday(), "Senin")
    intervals = schedule.get(day_name) or []
    if not intervals:
        return False
    current_minutes = (now_dt.hour * 60) + now_dt.minute
    for interval in intervals:
        parsed = _parse_schedule_range(interval)
        if not parsed:
            continue
        start_minutes, end_minutes = parsed
        if start_minutes <= end_minutes:
            if start_minutes <= current_minutes <= end_minutes:
                return True
        elif current_minutes >= start_minutes or current_minutes <= end_minutes:
            return True
    return False


def is_within_shopee_schedule(raw_schedule, now_dt: Optional[datetime] = None) -> bool:
    now_wib = now_dt or datetime.now(WIB)
    if now_wib.tzinfo is None:
        now_wib = now_wib.replace(tzinfo=WIB)
    else:
        now_wib = now_wib.astimezone(WIB)
    schedule = normalize_shopee_regular_hours(raw_schedule)
    if not schedule:
        return False
    return _is_within_normalized_schedule(schedule, now_wib)


def _normalize_persisted_shopee_status(value) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"ON", "OPEN"}:
        return "ON"
    if normalized == "PAUSE":
        return "PAUSE"
    if normalized in {"OFF", "CLOSED", "CLOSE"}:
        return "CLOSED"
    return "UNKNOWN"


def _normalize_live_state(value) -> str:
    normalized = _normalize_persisted_shopee_status(value)
    if normalized == "ON":
        return "OPEN"
    if normalized == "PAUSE":
        return "PAUSE"
    if normalized == "CLOSED":
        return "CLOSED"
    return "UNKNOWN"


def _normalize_desired_state(vercel_status, pause_until) -> str:
    if str(vercel_status or "").strip().upper() == "ON":
        return "OPEN"
    return "PAUSE" if _coerce_pause_until(pause_until) else "MANUAL_OFF"


def _is_subscription_active(subscription_status: Optional[str]) -> bool:
    normalized = str(subscription_status or "").strip().lower()
    return normalized not in {"expired", "kedaluwarsa", "inactive", "nonaktif"}


def _format_pause_until_local(pause_until, timezone: str) -> str:
    pause_until_dt = _coerce_pause_until(pause_until)
    if not pause_until_dt:
        return ""
    return pause_until_dt.astimezone(timezone_for(timezone)).strftime("%d/%m/%Y %H:%M %Z")


def _derive_display_status_bucket(live_state: str, display_toggle_on: bool, desired_state: str) -> str:
    if live_state == "OPEN":
        return "open"
    if live_state in {"PAUSE", "CLOSED"}:
        return "closed"
    if display_toggle_on:
        return "open"
    return "open" if desired_state == "OPEN" else "closed"


def derive_outlet_runtime_state(
    store: Dict[str, Any],
    now_dt: Optional[datetime] = None,
    normalized_schedule: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    timezone = normalize_timezone(store.get("timezone"))
    local_tz = timezone_for(timezone)
    now_wib = now_dt or datetime.now(local_tz)
    if now_wib.tzinfo is None:
        now_wib = now_wib.replace(tzinfo=local_tz)
    else:
        now_wib = now_wib.astimezone(local_tz)

    pause_until_dt = _coerce_pause_until(store.get("pause_until"))
    pause_until_label = _format_pause_until_local(pause_until_dt, timezone)
    desired_state = _normalize_desired_state(store.get("vercel_status"), pause_until_dt)
    live_state = _normalize_live_state(store.get("shopee_status"))
    schedule = normalized_schedule if normalized_schedule is not None else normalize_shopee_regular_hours(store.get("shopee_regular_hours"))
    schedule_available = _normalized_schedule_has_intervals(schedule)
    within_schedule = schedule_available and _is_within_normalized_schedule(schedule, now_wib)
    schedule_fetch_status = _derive_schedule_fetch_status(store, schedule_available=schedule_available)
    schedule_fetch_error = _clean_schedule_fetch_error(store.get("schedule_fetch_error"))
    is_suspended = bool(store.get("is_suspended")) or str(store.get("suspension_status") or "").upper() == "SUSPENDED"
    subscription_active = _is_subscription_active(store.get("subscription_status"))

    if is_suspended:
        bot_phase = "SUSPENDED"
        status_label = "Sedang Tutup • Dinonaktifkan admin"
        status_tone = "closed"
        display_note = (
            "Outlet dinonaktifkan admin. Menunggu bot menutup outlet di Shopee."
            if live_state == "OPEN"
            else "Otomatisasi dinonaktifkan oleh admin."
        )
    elif desired_state == "OPEN" and not schedule_available:
        if schedule_fetch_status == SCHEDULE_FETCH_EMPTY:
            bot_phase = SCHEDULE_FETCH_EMPTY
            status_label = "Jadwal Shopee belum diatur"
            status_tone = "closed"
            display_note = "Toggle aktif, tetapi jadwal operasional Shopee belum diatur di Shopee sehingga bot belum bisa memproses outlet."
        elif schedule_fetch_status == SCHEDULE_FETCH_RETRYING:
            bot_phase = SCHEDULE_FETCH_RETRYING
            status_label = "Gagal fetch jadwal, bot akan coba lagi"
            status_tone = "pending"
            display_note = "Toggle aktif. Bot belum berhasil fetch jadwal operasional Shopee dan akan mencoba lagi saat patroli berikutnya."
        else:
            bot_phase = SCHEDULE_FETCH_NOT_FETCHED_YET
            status_label = "Menunggu fetch jadwal"
            status_tone = "pending"
            display_note = "Toggle aktif. Bot menunggu fetch jadwal operasional Shopee sebelum memproses outlet."
    elif live_state == "UNKNOWN":
        bot_phase = "STATUS_UNKNOWN"
        status_label = "Status sedang dicek bot"
        status_tone = "pending"
        display_note = "Status live outlet masih diperiksa bot."
    elif desired_state in {"PAUSE", "MANUAL_OFF"} and live_state == "OPEN":
        bot_phase = "PENDING_PAUSE"
        status_label = "Sedang Buka • Menunggu bot menutup"
        status_tone = "pending"
        display_note = (
            "Permintaan tutup sementara sudah tersimpan. Menunggu bot menutup outlet."
            if desired_state == "PAUSE"
            else "Permintaan menonaktifkan otomatisasi sudah tersimpan. Menunggu bot menutup outlet."
        )
    elif desired_state == "OPEN" and live_state in {"PAUSE", "CLOSED"} and within_schedule:
        bot_phase = "PENDING_OPEN"
        status_label = "Sedang Tutup • Menunggu bot membuka"
        status_tone = "pending"
        if live_state == "CLOSED":
            display_note = "Outlet tertutup di Shopee padahal toggle aktif. Menunggu bot membuka kembali outlet."
        else:
            display_note = "Permintaan buka sudah tersimpan. Menunggu bot membuka outlet."
    elif desired_state == "OPEN" and not within_schedule:
        bot_phase = "WAITING_SCHEDULE"
        status_label = "Sedang Tutup • Di luar jadwal"
        status_tone = "closed"
        display_note = (
            "Di luar jadwal. Toggle aktif kembali saat jam operasional dimulai. "
            "Status live Shopee tetap ditampilkan terpisah."
        )
    elif desired_state == "MANUAL_OFF":
        bot_phase = "AUTOMATION_OFF"
        status_label = "Sedang Tutup • Otomatisasi nonaktif"
        status_tone = "closed"
        display_note = (
            "Otomatisasi tidak aktif karena masa layanan outlet sudah berakhir."
            if not subscription_active
            else "Nonaktif sampai diaktifkan kembali."
        )
    elif desired_state == "PAUSE" and live_state in {"PAUSE", "CLOSED"}:
        bot_phase = "IN_SYNC"
        status_label = "Tutup Sementara"
        status_tone = "paused"
        display_note = (
            f"Buka kembali otomatis pada {pause_until_label}."
            if pause_until_label
            else "Outlet sedang ditutup sementara."
        )
    elif desired_state == "OPEN" and live_state == "OPEN":
        bot_phase = "IN_SYNC"
        status_label = "Sedang Buka"
        status_tone = "open"
        display_note = "Outlet mengikuti jam operasional Shopee."
    else:
        bot_phase = "STATUS_UNKNOWN"
        status_label = "Status sedang dicek bot"
        status_tone = "pending"
        display_note = "Status outlet sedang dicocokkan ulang oleh bot."

    if is_suspended:
        display_toggle_reason = "SUSPENDED"
    elif not schedule_available:
        display_toggle_reason = schedule_fetch_status
    elif not within_schedule:
        display_toggle_reason = "OUTSIDE_SCHEDULE"
    else:
        display_toggle_reason = "READY"

    display_toggle_on = bool(
        desired_state == "OPEN"
        and not is_suspended
        and (not schedule_available or within_schedule)
    )
    display_toggle_disabled = bool(is_suspended or not schedule_available or not within_schedule)
    display_status_bucket = (
        "closed"
        if desired_state == "OPEN" and schedule_available and not within_schedule
        else "closed"
        if desired_state == "OPEN" and not schedule_available and schedule_fetch_status == SCHEDULE_FETCH_EMPTY
        else _derive_display_status_bucket(live_state, display_toggle_on, desired_state)
    )

    return {
        "desired_state": desired_state,
        "live_state": live_state,
        "bot_phase": bot_phase,
        "schedule_available": schedule_available,
        "schedule_fetch_status": schedule_fetch_status,
        "schedule_fetch_attempted_at": store.get("schedule_fetch_attempted_at"),
        "schedule_fetch_succeeded_at": store.get("schedule_fetch_succeeded_at"),
        "schedule_fetch_error": schedule_fetch_error,
        "within_operating_schedule": within_schedule,
        "display_toggle_on": display_toggle_on,
        "display_toggle_disabled": display_toggle_disabled,
        "display_toggle_reason": display_toggle_reason,
        "display_status_bucket": display_status_bucket,
        "display_status_label": status_label,
        "display_status_tone": status_tone,
        "display_note": display_note,
    }


def get_system_setting(key: str, default_val: str = "") -> str:
    with get_db_connection() as conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key=%s", (key,)).fetchone()
        if row:
            return row["value"]
        return default_val


def set_system_setting(key: str, value: str) -> bool:
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO system_settings (key, value, updated_at) VALUES (%s, %s, now()) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
            (key, value)
        )
        return True


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "mitra").lower()).strip("-") or "mitra"


def _new_link_slug(owner: str) -> str:
    return f"{_slug(owner)}-{secrets.token_urlsafe(16).rstrip('=')[:22]}"


def _context(conn, owner: str, merchant_name: str, dashboard_password: str = "", base_url: str = "", google_email: Optional[str] = None):
    owner_clean = (owner or "Unassigned").strip()
    portal_clean = (merchant_name or "Unknown Merchant").strip()

    if google_email:
        email_clean = google_email.strip()
        if email_clean:
            existing = conn.execute(
                "SELECT username FROM dashboard_accounts WHERE LOWER(google_email) = LOWER(%s) AND LOWER(username) != LOWER(%s)",
                (email_clean, owner_clean)
            ).fetchone()
            if existing:
                raise ValueError("Email Google sudah terdaftar.")

    merchant = conn.execute("SELECT id FROM merchants WHERE name=%s", (owner_clean,)).fetchone()
    if not merchant:
        merchant = conn.execute("INSERT INTO merchants (name) VALUES (%s) RETURNING id", (owner_clean,)).fetchone()
    merchant_id = merchant["id"]

    portal = conn.execute(
        "INSERT INTO portals (merchant_id,name) VALUES (%s,%s) ON CONFLICT (merchant_id,name) DO UPDATE SET updated_at=now() RETURNING id",
        (merchant_id, portal_clean)
    ).fetchone()

    base = (base_url or os.getenv("APP_BASE_URL", "http://localhost:3001")).rstrip("/")
    account = conn.execute("SELECT * FROM dashboard_accounts WHERE username=%s", (owner_clean,)).fetchone()
    if not account:
        slug = _new_link_slug(owner_clean)
        account = conn.execute(
            "INSERT INTO dashboard_accounts (merchant_id,username,password_plain,link_slug,dashboard_url,role,google_email) VALUES (%s,%s,%s,%s,%s,'MERCHANT',%s) RETURNING *",
            (merchant_id, owner_clean, dashboard_password or "Master@00@", slug, f"{base}/mitra/{slug}", google_email)
        ).fetchone()
    else:
        updates = []
        params = []
        if not account.get("link_slug"):
            new_slug = _new_link_slug(owner_clean)
            updates.extend(["link_slug=%s", "dashboard_url=%s"])
            params.extend([new_slug, f"{base}/mitra/{new_slug}"])
        if dashboard_password:
            updates.append("password_plain=%s")
            params.append(dashboard_password)
        if base_url:
            target_url = f"{base}/mitra/{account['link_slug']}" if account.get("link_slug") else None
            if target_url:
                updates.append("dashboard_url=%s")
                params.append(target_url)
        if google_email is not None:
            updates.append("google_email=%s")
            params.append(google_email.strip() or None)
        
        if updates:
            updates.append("updated_at=now()")
            query = f"UPDATE dashboard_accounts SET {', '.join(updates)} WHERE id=%s"
            conn.execute(query, (*params, account["id"]))
            account = conn.execute("SELECT * FROM dashboard_accounts WHERE id=%s", (account["id"],)).fetchone()

    bot = conn.execute("SELECT id FROM bot_accounts WHERE username=%s", (BOT_USERNAME,)).fetchone()
    if bot:
        conn.execute(
            "INSERT INTO bot_merchant_assignments (bot_account_id,merchant_id) VALUES (%s,%s) ON CONFLICT (bot_account_id,merchant_id) DO UPDATE SET is_active=true",
            (bot["id"], merchant_id)
        )
    return merchant_id, portal["id"], account


def save_or_update_store(store_id: str, store_name: str, merchant_name: str, account_username: str = "", account_password: str = "", nama_pemilik: str = "", paket: str = "3 Bulan", tanggal_mulai_layanan: str = "", tanggal_berakhir_layanan: str = "", vercel_link: str = "", vercel_password: str = "", vercel_status: str = "ON", shopee_status: str = "UNKNOWN", subscription_status: str = "Aktif", is_suspended: bool = False, alasan_penangguhan: str = "", pause_until: Optional[str] = None, regular_hours: Optional[Dict] = None, special_hours: str = "", base_url: str = "", google_email: Optional[str] = None, is_active: bool = True, **_ignored) -> Dict:
    with get_db_connection() as conn:
        merchant_id, portal_id, account = _context(conn, nama_pemilik, merchant_name, vercel_password, base_url=base_url, google_email=google_email)
        existing_account = conn.execute("SELECT id FROM shopee_accounts WHERE portal_id=%s AND username=%s", (portal_id, account_username or BOT_USERNAME)).fetchone()
        if existing_account:
            shopee_account_id = existing_account["id"]
            if account_password:
                conn.execute("UPDATE shopee_accounts SET password_plain=%s,updated_at=now() WHERE id=%s", (account_password, shopee_account_id))
        else:
            shopee_account_id = conn.execute("INSERT INTO shopee_accounts (portal_id,merchant_id_external,username,password_plain) VALUES (%s,'',%s,%s) RETURNING id", (portal_id, account_username or BOT_USERNAME, account_password or BOT_PASSWORD)).fetchone()["id"]
        outlet = conn.execute("INSERT INTO outlets (merchant_id,portal_id,shopee_account_id,store_id,long_name,special_hours,is_active) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (store_id) DO UPDATE SET merchant_id=EXCLUDED.merchant_id,portal_id=EXCLUDED.portal_id,shopee_account_id=EXCLUDED.shopee_account_id,long_name=EXCLUDED.long_name,special_hours=EXCLUDED.special_hours,is_active=EXCLUDED.is_active,updated_at=now() RETURNING id", (merchant_id, portal_id, shopee_account_id, store_id, store_name or store_id, special_hours, is_active)).fetchone()
        outlet_id = outlet["id"]
        conn.execute("INSERT INTO outlet_states (outlet_id,vercel_status,shopee_actual_status,suspension_status,suspension_reason,pause_until) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (outlet_id) DO UPDATE SET updated_at=now()", (outlet_id, (vercel_status or "OFF").upper(), _normalize_persisted_shopee_status(shopee_status), "SUSPENDED" if is_suspended else "ACTIVE", alasan_penangguhan, pause_until))
        code = (paket or "3_MONTHS").upper().replace(" ", "_")
        code = code if code in {"3_MONTHS", "6_MONTHS", "12_MONTHS"} else "3_MONTHS"
        plan = conn.execute("SELECT id, total_months FROM subscription_plans WHERE code=%s", (code,)).fetchone()
        if plan:
            start_dt = tanggal_mulai_layanan or datetime.utcnow().strftime("%Y-%m-%d")
            if not tanggal_berakhir_layanan:
                months = plan["total_months"] if plan and "total_months" in plan else 3
                calc_row = conn.execute("SELECT (%s::date + (%s || ' months')::interval)::date AS end_date", (start_dt, months)).fetchone()
                end_dt = str(calc_row["end_date"])
            else:
                end_dt = tanggal_berakhir_layanan
            conn.execute("DELETE FROM subscriptions WHERE outlet_id=%s", (outlet_id,))
            conn.execute("INSERT INTO subscriptions (outlet_id,plan_id,start_date,end_date,status) VALUES (%s,%s,%s,%s,%s)", (outlet_id, plan["id"], start_dt, end_dt, "ACTIVE" if (subscription_status or "").lower() == "aktif" else "EXPIRED"))
        if regular_hours:
            names = ("Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu")
            for weekday, name in enumerate(names):
                value = regular_hours.get(name, "") or ""
                opened, closed = value.split("-", 1) if "-" in value else (None, None)
                conn.execute("INSERT INTO operating_hours (outlet_id,weekday,open_time,close_time,is_closed) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (outlet_id,weekday) DO UPDATE SET open_time=EXCLUDED.open_time,close_time=EXCLUDED.close_time,is_closed=EXCLUDED.is_closed", (outlet_id, weekday, opened or None, closed or None, not bool(value)))
        return dict(account) if account else {}


def format_last_action(raw_action: Optional[str]) -> str:
    if not raw_action:
        return "no change"
    act = str(raw_action).strip().upper()
    if act in ("ACTION_OPEN", "USER_RESUME_STORE", "ADMIN_RESUME_STORE", "OPEN_STORE", "OPEN"):
        return "action open"
    elif act in ("ACTION_CLOSE", "USER_PAUSE_STORE", "ADMIN_PAUSE_STORE", "CLOSE_STORE", "CLOSE", "PAUSE"):
        return "action close"
    elif act in ("NO_CHANGE", "NONE"):
        return "no change"
    else:
        return "no change"


def _store_query(where: str = "", params=()) -> List[Dict]:
    query = """SELECT o.id AS outlet_uuid,o.store_id,o.long_name AS store_name,o.long_name,'' AS kepemilikan,o.special_hours,p.name AS merchant_name,p.name AS nama_portal,m.name AS nama_pemilik,m.id AS merchant_id,COALESCE(sa.username,%s) AS account_username,COALESCE(sa.phone,'') AS shopee_phone,COALESCE(sa.password_plain,'') AS shopee_password,da.password_plain AS vercel_password,da.dashboard_url AS vercel_link,da.google_email,os.vercel_status,os.shopee_actual_status AS shopee_status,os.shopee_regular_hours,os.schedule_fetch_status,to_char(os.schedule_fetch_attempted_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS schedule_fetch_attempted_at,to_char(os.schedule_fetch_succeeded_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS schedule_fetch_succeeded_at,COALESCE(os.schedule_fetch_error, '') AS schedule_fetch_error,os.suspension_status,(os.suspension_status='SUSPENDED') AS is_suspended,os.suspension_reason AS alasan_penangguhan,os.pause_until::text AS pause_until,to_char(os.last_checked_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS last_synced_at,al.action AS last_action_raw,tl.action AS last_toggle_action_raw,COALESCE(tl.reason, '') AS last_toggle_reason,tl.checked_at AS last_toggle_at,COALESCE(CASE WHEN s.status='ACTIVE' THEN 'Aktif' WHEN s.status='EXPIRED' THEN 'Kedaluwarsa' ELSE s.status END,CASE WHEN s.end_date>=CURRENT_DATE THEN 'Aktif' ELSE 'Kedaluwarsa' END,'Aktif') AS subscription_status,s.start_date::text AS tanggal_mulai_layanan,s.end_date::text AS tanggal_berakhir_layanan,sp.name AS paket FROM outlets o JOIN merchants m ON m.id=o.merchant_id JOIN portals p ON p.id=o.portal_id LEFT JOIN shopee_accounts sa ON sa.id=o.shopee_account_id LEFT JOIN dashboard_accounts da ON da.merchant_id=m.id AND da.role='MERCHANT' LEFT JOIN outlet_states os ON os.outlet_id=o.id LEFT JOIN LATERAL (SELECT action FROM automation_logs WHERE outlet_id=o.id ORDER BY id DESC LIMIT 1) al ON true LEFT JOIN LATERAL (SELECT action, COALESCE(reason, '') AS reason, to_char(checked_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS checked_at FROM automation_logs WHERE outlet_id=o.id AND action IN ('ACTION_OPEN','ACTION_CLOSE','USER_PAUSE_STORE','USER_RESUME_STORE','ADMIN_PAUSE_STORE','ADMIN_RESUME_STORE','OPEN_STORE','CLOSE_STORE','OPEN','CLOSE','PAUSE') ORDER BY id DESC LIMIT 1) tl ON true LEFT JOIN LATERAL (SELECT * FROM subscriptions sx WHERE sx.outlet_id=o.id ORDER BY sx.end_date DESC LIMIT 1) s ON true LEFT JOIN subscription_plans sp ON sp.id=s.plan_id"""
    if where: query += " WHERE " + where
    # Virtual Brand outlets are controlled exclusively through vb_brands and
    # must not appear in the regular outlet dashboard or bot-oc worker scope.
    vb_exclusion = " AND NOT EXISTS (SELECT 1 FROM vb_brand_outlets vb_filter WHERE vb_filter.outlet_id=o.id)"
    query += (" AND o.is_active=true" if where else " WHERE o.is_active=true") + vb_exclusion
    query += " ORDER BY m.name,p.name,o.store_id"
    with get_db_connection() as conn:
        rows = [dict(row) for row in conn.execute(query, (BOT_USERNAME, *params)).fetchall()]
        if not rows:
            return []
        now_dt = datetime.now(WIB)
        outlet_ids = [r["outlet_uuid"] for r in rows]
        hours_rows = conn.execute(
            "SELECT outlet_id, weekday, open_time::text, close_time::text, is_closed FROM operating_hours WHERE outlet_id = ANY(%s)",
            (outlet_ids,)
        ).fetchall()
        hours_map = {}
        names = ("Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu")
        for hr in hours_rows:
            oid = hr["outlet_id"]
            if oid not in hours_map:
                hours_map[oid] = {}
            if not hr["is_closed"] and hr["open_time"] and hr["close_time"]:
                ot = hr["open_time"][:5]
                ct = hr["close_time"][:5]
                hours_map[oid][names[hr["weekday"]]] = f"{ot}-{ct}"
            else:
                hours_map[oid][names[hr["weekday"]]] = ""
        pause_mode_rows = conn.execute(
            "SELECT outlet_id, pause_mode FROM outlet_states WHERE outlet_id = ANY(%s)",
            (outlet_ids,),
        ).fetchall()
        pause_mode_map = {row["outlet_id"]: row["pause_mode"] for row in pause_mode_rows}
        timezone_rows = conn.execute(
            "SELECT outlet_id, timezone FROM outlet_states WHERE outlet_id = ANY(%s)",
            (outlet_ids,),
        ).fetchall()
        timezone_map = {row["outlet_id"]: normalize_timezone(row["timezone"]) for row in timezone_rows}
        for r in rows:
            r["regular_hours"] = hours_map.get(r["outlet_uuid"], {})
            r["pause_mode"] = pause_mode_map.get(r["outlet_uuid"])
            r["timezone"] = timezone_map.get(r["outlet_uuid"], "Asia/Jakarta")
            r["special_hours"] = r.get("special_hours") or ""
            r["shopee_status"] = _normalize_persisted_shopee_status(r.get("shopee_status"))
            r["shopee_regular_hours"] = normalize_shopee_regular_hours(r.get("shopee_regular_hours"))
            r["last_action"] = format_last_action(r.get("last_action_raw"))
            r.update(derive_outlet_runtime_state(r, now_dt=now_dt, normalized_schedule=r["shopee_regular_hours"]))
        return rows


def get_all_stores(): return _store_query()
def get_store_by_id(store_id):
    rows = _store_query("o.store_id=%s", (store_id,)); return rows[0] if rows else None

def deactivate_store(store_id: str) -> bool:
    with get_db_connection() as conn:
        result = conn.execute("UPDATE outlets SET is_active=false,updated_at=now() WHERE store_id=%s", (store_id,))
        return result.rowcount > 0

def _public_store(store):
    item = dict(store); item.update({"account_username": BOT_USERNAME, "merchant_name": store.get("merchant_name", ""), "is_suspended": store.get("suspension_status") == "SUSPENDED"}); return item
def admin_get_all_users_with_stores():
    grouped = {}
    for store in _store_query():
        owner = store.get("nama_pemilik") or "Unassigned"
        grouped.setdefault(owner, {"nama_pemilik": owner, "nama_portal": store.get("nama_portal", ""), "total_outlets": 0, "outlets": []})
        grouped[owner]["outlets"].append(_public_store(store)); grouped[owner]["total_outlets"] += 1
    return list(grouped.values())
def user_get_outlets(nama_pemilik): return [_public_store(row) for row in _store_query("m.name=%s", (nama_pemilik,))]

def sync_expired_user_pauses():
    """Mark completed user pauses ON after Shopee's scheduled auto-open."""
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE outlet_states os
               SET vercel_status='ON', pause_until=NULL, updated_at=now()
             WHERE os.vercel_status='OFF'
               AND os.pause_until IS NOT NULL
               AND os.pause_until <= now()
               AND os.suspension_status='ACTIVE'
               AND NOT EXISTS (
                   SELECT 1 FROM subscriptions sx
                    WHERE sx.outlet_id=os.outlet_id
                      AND sx.end_date<CURRENT_DATE
                      AND sx.status<>'CANCELLED'
               )
        """)

def admin_generate_user_link(nama_pemilik, passcode=None, base_url=None):
    with get_db_connection() as conn:
        merchant = conn.execute("SELECT id FROM merchants WHERE name=%s", (nama_pemilik,)).fetchone()
        if not merchant: merchant = conn.execute("INSERT INTO merchants (name) VALUES (%s) RETURNING id", (nama_pemilik,)).fetchone()
        password = passcode or "Master@00@"; slug = _new_link_slug(nama_pemilik); base = (base_url or os.getenv("APP_BASE_URL", "http://localhost:3001")).rstrip("/")
        row = conn.execute("INSERT INTO dashboard_accounts (merchant_id,username,password_plain,link_slug,dashboard_url,role) VALUES (%s,%s,%s,%s,%s,'MERCHANT') ON CONFLICT (username) DO UPDATE SET password_plain=EXCLUDED.password_plain,link_slug=EXCLUDED.link_slug,dashboard_url=EXCLUDED.dashboard_url RETURNING link_slug,dashboard_url", (merchant["id"], nama_pemilik, password, slug, f"{base}/mitra/{slug}")).fetchone()
    return {"nama_pemilik": nama_pemilik, "passcode": password, "link_slug": row["link_slug"], "full_url": row["dashboard_url"]}

def user_authenticate(passcode, slug=None):
    with get_db_connection() as conn:
        if slug:
            row = conn.execute("SELECT username AS nama_pemilik,password_plain AS password,link_slug FROM dashboard_accounts WHERE link_slug=%s AND password_plain=%s AND role='MERCHANT' AND is_active=true LIMIT 1", (slug, passcode)).fetchone()
        else:
            # Keep /app and older integrations working while slug-based links use scoped access.
            row = conn.execute("SELECT username AS nama_pemilik,password_plain AS password,link_slug FROM dashboard_accounts WHERE password_plain=%s AND role='MERCHANT' AND is_active=true LIMIT 1", (passcode,)).fetchone()
    return dict(row) if row else None


def admin_authenticate(username, password):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id,username,role FROM dashboard_accounts WHERE username=%s AND password_plain=%s AND role='ADMIN' AND is_active=true LIMIT 1",
            (username, password),
        ).fetchone()
        if row:
            conn.execute("UPDATE dashboard_accounts SET last_login_at=now(),updated_at=now() WHERE id=%s", (row["id"],))
    return dict(row) if row else None


def google_authenticate(email: str):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active, password_plain FROM dashboard_accounts WHERE LOWER(google_email)=LOWER(%s) AND is_active=true LIMIT 1",
            (email,),
        ).fetchone()
        if row:
            conn.execute("UPDATE dashboard_accounts SET last_login_at=now(), updated_at=now() WHERE id=%s", (row["id"],))
            return dict(row)
    return None


def get_dashboard_account_by_id(account_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT id, username, role, is_active, google_email FROM dashboard_accounts WHERE id=%s LIMIT 1", (account_id,)).fetchone()
    return dict(row) if row else None


def admin_list_accounts():
    with get_db_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT id,username,role,is_active,google_email,last_login_at,created_at FROM dashboard_accounts WHERE role='ADMIN' ORDER BY username").fetchall()]


def admin_update_account(account_id, username=None, password=None, google_email=None):
    with get_db_connection() as conn:
        account = conn.execute("SELECT id,username,role,is_active FROM dashboard_accounts WHERE id=%s AND role='ADMIN'", (account_id,)).fetchone()
        if not account:
            return None
        next_username = username.strip() if username is not None else account["username"]
        if not next_username:
            raise ValueError("Username tidak boleh kosong.")
        duplicate = conn.execute("SELECT id FROM dashboard_accounts WHERE username=%s AND id<>%s", (next_username, account_id)).fetchone()
        if duplicate:
            raise ValueError("Username sudah digunakan akun lain.")
        
        email_clean = google_email.strip() if google_email is not None else None
        if email_clean:
            duplicate_email = conn.execute("SELECT id FROM dashboard_accounts WHERE LOWER(google_email)=LOWER(%s) AND id<>%s", (email_clean, account_id)).fetchone()
            if duplicate_email:
                raise ValueError("Email Google sudah digunakan akun lain.")

        if password is not None:
            conn.execute("UPDATE dashboard_accounts SET username=%s,password_plain=%s,google_email=%s,updated_at=now() WHERE id=%s", (next_username, password, email_clean, account_id))
        else:
            conn.execute("UPDATE dashboard_accounts SET username=%s,google_email=%s,updated_at=now() WHERE id=%s", (next_username, email_clean, account_id))
        row = conn.execute("SELECT id,username,role,is_active,google_email FROM dashboard_accounts WHERE id=%s", (account_id,)).fetchone()
    return dict(row)


def admin_create_account(username, password, google_email=None):
    username = username.strip()
    if not username or not password:
        raise ValueError("Username dan password wajib diisi.")
    email_clean = google_email.strip() if google_email else None
    with get_db_connection() as conn:
        if conn.execute("SELECT id FROM dashboard_accounts WHERE username=%s", (username,)).fetchone():
            raise ValueError("Username sudah digunakan akun lain.")
        if email_clean:
            if conn.execute("SELECT id FROM dashboard_accounts WHERE LOWER(google_email)=LOWER(%s)", (email_clean,)).fetchone():
                raise ValueError("Email Google sudah digunakan akun lain.")
        row = conn.execute("INSERT INTO dashboard_accounts (username,password_plain,role,is_active,google_email) VALUES (%s,%s,'ADMIN',true,%s) RETURNING id,username,role,is_active,google_email", (username, password, email_clean)).fetchone()
    return dict(row)
def update_vercel_toggle(store_id, status, pause_until=None):
    pause_until = _coerce_pause_until(pause_until)
    with get_db_connection() as conn: conn.execute("""UPDATE outlet_states os SET vercel_status=CASE WHEN os.suspension_status='SUSPENDED' OR EXISTS (SELECT 1 FROM subscriptions sx WHERE sx.outlet_id=os.outlet_id AND sx.end_date<CURRENT_DATE AND sx.status<>'CANCELLED') THEN 'OFF' ELSE %s END,pause_until=%s,updated_at=now() FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""", (status.upper(), pause_until, store_id))


def _apply_toggle_transaction(
    store_id: str,
    status: str,
    pause_until,
    action: str,
    target_state: str,
    reason: str,
    pause_mode: Optional[str],
    reject_suspended: bool,
    reject_expired_on: bool,
) -> Dict[str, Any]:
    """Serialize one outlet toggle and its audit log in a single transaction."""
    normalized_status = str(status or "").upper()
    if normalized_status not in {"ON", "OFF"}:
        return {"success": False, "code": "invalid_status", "detail": "Status toggle tidak valid."}

    pause_until = _coerce_pause_until(pause_until)

    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT o.id AS outlet_id, o.store_id, o.long_name AS store_name,
                   m.name AS owner_name,
                   os.vercel_status, os.shopee_actual_status, os.suspension_status,
                   os.suspension_reason,
                   EXISTS (
                       SELECT 1 FROM subscriptions sx
                        WHERE sx.outlet_id=o.id
                          AND sx.end_date<CURRENT_DATE
                          AND sx.status<>'CANCELLED'
                   ) AS subscription_expired
              FROM outlets o
              JOIN merchants m ON m.id=o.merchant_id
              JOIN outlet_states os ON os.outlet_id=o.id
             WHERE o.store_id=%s AND o.is_active=true
             FOR UPDATE OF os
            """,
            (store_id,),
        ).fetchone()
        if not row:
            return {"success": False, "code": "not_found", "detail": f"Store ID '{store_id}' not found."}

        if reject_suspended and row["suspension_status"] == "SUSPENDED":
            suspension_reason = row.get("suspension_reason") or "Tindakan admin"
            return {
                "success": False,
                "code": "suspended",
                "detail": f"Outlet ditangguhkan oleh Admin (Alasan: {suspension_reason}). Silakan hubungi CS.",
            }
        if reject_expired_on and normalized_status == "ON" and row["subscription_expired"]:
            return {"success": False, "code": "subscription_expired", "detail": "Subscription outlet sudah berakhir."}

        next_pause_until = pause_until if normalized_status == "OFF" else None
        effective_status = "OFF" if row["suspension_status"] == "SUSPENDED" or row["subscription_expired"] else normalized_status
        updated = conn.execute(
            """
            UPDATE outlet_states
               SET vercel_status=%s,
                   pause_until=%s,
                   pause_mode=%s,
                   last_action_at=now(),
                   last_checked_at=now(),
                   updated_at=now()
             WHERE outlet_id=%s
         RETURNING vercel_status, pause_until::text AS pause_until,
                   last_action_at::text AS changed_at
            """,
            (effective_status, next_pause_until, pause_mode if normalized_status == "OFF" else None, row["outlet_id"]),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO automation_logs
                (outlet_id, mode, suspension_status, subscription_status,
                 vercel_status_before, shopee_status_before, target_status,
                 action, success, error_message, reason)
            VALUES (%s, 'REGULAR', %s, 'ACTIVE', %s, %s, %s, %s, true, NULL, %s)
            """,
            (
                row["outlet_id"],
                row["suspension_status"],
                row["vercel_status"],
                row["shopee_actual_status"],
                target_state,
                action,
                reason,
            ),
        )
        return {
            "success": True,
            "store_id": row["store_id"],
            "store_name": row["store_name"],
            "owner_name": row["owner_name"],
            "vercel_status": updated["vercel_status"],
            "pause_until": updated["pause_until"],
            "pause_mode": pause_mode if normalized_status == "OFF" else None,
            "changed_at": updated["changed_at"],
            "reason": reason,
        }


def apply_user_toggle(store_id: str, status: str, pause_until, action: str, target_state: str, reason: str, pause_mode: Optional[str] = None) -> Dict[str, Any]:
    return _apply_toggle_transaction(
        store_id, status, pause_until, action, target_state, reason, pause_mode,
        reject_suspended=True,
        reject_expired_on=True,
    )


def apply_admin_toggle(store_id: str, status: str, pause_until, action: str, target_state: str, reason: str, pause_mode: Optional[str] = None) -> Dict[str, Any]:
    return _apply_toggle_transaction(
        store_id, status, pause_until, action, target_state, reason, pause_mode,
        reject_suspended=False,
        reject_expired_on=False,
    )


def admin_set_suspension(store_id, penangguhan, alasan=""):
    suspended = penangguhan.lower() == "ya"
    with get_db_connection() as conn: conn.execute("UPDATE outlet_states os SET suspension_status=%s,suspension_reason=%s,vercel_status=CASE WHEN %s THEN 'OFF' ELSE vercel_status END,updated_at=now() FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s", ("SUSPENDED" if suspended else "ACTIVE", alasan, suspended, store_id))
def admin_renew_subscription(store_id, new_expiry_date):
    with get_db_connection() as conn: conn.execute("UPDATE subscriptions s SET end_date=%s,status='ACTIVE',updated_at=now() FROM outlets o WHERE o.id=s.outlet_id AND o.store_id=%s", (new_expiry_date, store_id))
def admin_edit_outlet(store_id: str, nama_pemilik: Optional[str] = None, nama_portal: Optional[str] = None, nama_panjang_outlet: Optional[str] = None, paket: Optional[str] = None, dashboard_password: Optional[str] = None, google_email: Optional[str] = None) -> bool:
    with get_db_connection() as conn:
        outlet = conn.execute("SELECT id, merchant_id, portal_id FROM outlets WHERE store_id=%s", (store_id,)).fetchone()
        if not outlet:
            return False
        oid = outlet["id"]
        mid = outlet["merchant_id"]
        pid = outlet["portal_id"]
        if nama_panjang_outlet is not None and nama_panjang_outlet.strip():
            conn.execute("UPDATE outlets SET long_name=%s, updated_at=now() WHERE id=%s", (nama_panjang_outlet.strip(), oid))
        if nama_pemilik is not None and nama_pemilik.strip():
            new_owner = nama_pemilik.strip()
            conn.execute("UPDATE merchants SET name=%s, updated_at=now() WHERE id=%s", (new_owner, mid))
            conn.execute("UPDATE dashboard_accounts SET username=%s, updated_at=now() WHERE merchant_id=%s AND role='MERCHANT'", (new_owner, mid))
        if nama_portal is not None and nama_portal.strip():
            new_portal = nama_portal.strip()
            conn.execute("UPDATE portals SET name=%s, updated_at=now() WHERE id=%s", (new_portal, pid))
        if dashboard_password is not None and dashboard_password.strip():
            conn.execute("UPDATE dashboard_accounts SET password_plain=%s, updated_at=now() WHERE merchant_id=%s AND role='MERCHANT'", (dashboard_password.strip(), mid))
        if google_email is not None:
            email_clean = google_email.strip()
            if email_clean:
                existing = conn.execute(
                    "SELECT username FROM dashboard_accounts WHERE LOWER(google_email) = LOWER(%s) AND (merchant_id IS NULL OR merchant_id != %s)",
                    (email_clean, mid)
                ).fetchone()
                if existing:
                    raise ValueError("Email Google sudah terdaftar.")
            conn.execute("UPDATE dashboard_accounts SET google_email=%s, updated_at=now() WHERE merchant_id=%s AND role='MERCHANT'", (email_clean or None, mid))
        if paket is not None and paket.strip():
            code = paket.strip().upper().replace(" ", "_")
            if code in {"3_MONTHS", "6_MONTHS", "12_MONTHS"}:
                plan = conn.execute("SELECT id FROM subscription_plans WHERE code=%s", (code,)).fetchone()
                if plan:
                    conn.execute("UPDATE subscriptions SET plan_id=%s, updated_at=now() WHERE outlet_id=%s", (plan["id"], oid))
        return True

def update_shopee_actual_status(store_id, status):
    with get_db_connection() as conn: conn.execute("UPDATE outlet_states os SET shopee_actual_status=%s,updated_at=now() FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s", (_normalize_persisted_shopee_status(status), store_id))

def update_shopee_regular_hours(store_id: str, regular_hours: Dict[str, List[str]]) -> None:
    normalized_hours = normalize_shopee_regular_hours(regular_hours)
    if not _normalized_schedule_has_intervals(normalized_hours):
        mark_schedule_fetch_empty(store_id)
        return
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE outlet_states os
                  SET shopee_regular_hours=%s,
                      schedule_fetch_status=%s,
                      schedule_fetch_attempted_at=now(),
                      schedule_fetch_succeeded_at=now(),
                      schedule_fetch_error=NULL,
                      last_checked_at=now(),
                      updated_at=now()
                 FROM outlets o
                WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (json.dumps(normalized_hours), SCHEDULE_FETCH_READY, store_id),
        )


def mark_schedule_fetch_empty(store_id: str) -> None:
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE outlet_states os
                  SET shopee_regular_hours=%s,
                      schedule_fetch_status=%s,
                      schedule_fetch_attempted_at=now(),
                      schedule_fetch_succeeded_at=now(),
                      schedule_fetch_error=NULL,
                      last_checked_at=now(),
                      updated_at=now()
                 FROM outlets o
                WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (json.dumps({}), SCHEDULE_FETCH_EMPTY, store_id),
        )


def mark_schedule_fetch_retry(store_id: str, error_message: Optional[str]) -> None:
    error_text = _clean_schedule_fetch_error(error_message) or "Bot belum berhasil fetch jadwal Shopee."
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE outlet_states os
                  SET schedule_fetch_status=%s,
                      schedule_fetch_attempted_at=now(),
                      schedule_fetch_error=%s,
                      last_checked_at=now(),
                      updated_at=now()
                 FROM outlets o
                WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (SCHEDULE_FETCH_RETRYING, error_text, store_id),
        )


def update_outlet_timezone(store_id: str, timezone: str) -> None:
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE outlet_states os SET timezone=%s, updated_at=now() FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s",
            (normalize_timezone(timezone), store_id),
        )
def record_log(store_id, store_name, action, target_state, reason, success=True, error_message=None, mode="REGULAR"):
    with get_db_connection() as conn:
        outlet = conn.execute("SELECT id FROM outlets WHERE store_id=%s", (store_id,)).fetchone()
        if not outlet: return
        row = conn.execute("SELECT vercel_status,shopee_actual_status,suspension_status FROM outlet_states WHERE outlet_id=%s", (outlet["id"],)).fetchone() or {}
        conn.execute("INSERT INTO automation_logs (outlet_id,mode,suspension_status,subscription_status,vercel_status_before,shopee_status_before,target_status,action,success,error_message,reason) VALUES (%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s,%s,%s)", (outlet["id"], mode, row.get("suspension_status", "ACTIVE"), row.get("vercel_status", "OFF"), row.get("shopee_actual_status", "UNKNOWN"), target_state, action, success, error_message, reason))
        if not success:
            conn.execute("""INSERT INTO automation_errors
                (mode, outlet_id, store_id, merchant_name, action, attempt_count, error_type, error_message)
                SELECT %s, o.id, o.store_id, p.name, %s, 1, 'ACTION_FAILED', %s
                FROM outlets o JOIN portals p ON p.id=o.portal_id WHERE o.id=%s""",
                (mode, action, error_message or reason or "Automation action failed", outlet["id"]))
        conn.execute("UPDATE outlet_states SET last_action_at=now(), last_checked_at=now(), updated_at=now() WHERE outlet_id=%s", (outlet["id"],))
def get_recent_logs(limit=50, store_ids=None):
    query = """
        SELECT
            al.id,
            to_char(al.checked_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS timestamp,
            COALESCE(o.store_id, 'SYSTEM') AS store_id,
            COALESCE(o.long_name, 'Bot system') AS store_name,
            al.action,
            al.target_status AS target_state,
            COALESCE(al.reason, '') AS reason
        FROM automation_logs al
        LEFT JOIN outlets o ON o.id = al.outlet_id
    """
    params = []
    if store_ids:
        query += " WHERE o.store_id = ANY(%s)"
        params.append(list(store_ids))
    query += " ORDER BY al.id DESC LIMIT %s"
    params.append(limit)
    with get_db_connection() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_log_overview(limit=40):
    """Return compact two-bot activity plus traceable outlet errors."""
    with get_db_connection() as conn:
        summary_rows = conn.execute(
            """SELECT CASE WHEN al.mode = 'VB' THEN 'VB' ELSE 'REGULAR' END AS mode,
                      COUNT(*)::int AS event_count,
                      to_char(MAX(al.checked_at) AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS last_event_at
               FROM automation_logs al
               WHERE al.checked_at >= now() - interval '24 hours'
               GROUP BY CASE WHEN al.mode = 'VB' THEN 'VB' ELSE 'REGULAR' END"""
        ).fetchall()
        summary = {
            "REGULAR": {"event_count": 0, "last_event_at": None},
            "VB": {"event_count": 0, "last_event_at": None},
        }
        for row in summary_rows:
            summary[row["mode"]] = dict(row)["event_count"] and {
                "event_count": row["event_count"],
                "last_event_at": row["last_event_at"],
            } or {"event_count": 0, "last_event_at": row["last_event_at"]}

        recent = list(conn.execute(
            """SELECT al.id, to_char(al.checked_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS timestamp,
                      CASE WHEN al.mode = 'VB' THEN 'VB' ELSE 'REGULAR' END AS mode,
                      COALESCE(o.store_id, 'SYSTEM') AS store_id,
                      COALESCE(o.long_name, b.name, 'Bot system') AS store_name,
                      b.name AS brand_name, p.name AS merchant_name,
                      al.action, al.target_status AS target_state,
                      al.success, COALESCE(al.reason, '') AS reason
               FROM automation_logs al
               LEFT JOIN outlets o ON o.id=al.outlet_id
               LEFT JOIN vb_brands b ON b.id=al.vb_brand_id
               LEFT JOIN portals p ON p.id=o.portal_id
               ORDER BY al.id DESC LIMIT %s""", (limit,)
        ).fetchall())
        errors = list(conn.execute(
            """SELECT ae.id, to_char(ae.created_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS timestamp, ae.mode,
                      ae.store_id, COALESCE(ae.merchant_name, p.name, '') AS merchant_name,
                      b.name AS brand_name, ae.action, ae.attempt_count,
                      ae.error_type, ae.error_message
               FROM automation_errors ae
               LEFT JOIN outlets o ON o.id=ae.outlet_id
               LEFT JOIN portals p ON p.id=o.portal_id
               LEFT JOIN vb_brands b ON b.id=ae.vb_brand_id
               ORDER BY ae.id DESC LIMIT %s""", (limit,)
        ).fetchall())
        errors.extend(conn.execute(
            """SELECT al.id, to_char(al.checked_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS timestamp, 'REGULAR' AS mode,
                      COALESCE(o.store_id, 'SYSTEM') AS store_id,
                      p.name AS merchant_name, NULL AS brand_name,
                      al.action, 1 AS attempt_count, 'AUTOMATION_LOG_ERROR' AS error_type,
                      COALESCE(al.error_message, al.reason, 'Automation action failed') AS error_message
               FROM automation_logs al
               LEFT JOIN outlets o ON o.id=al.outlet_id
               LEFT JOIN portals p ON p.id=o.portal_id
               WHERE COALESCE(al.mode, 'OUTLET') <> 'VB' AND (al.success=false OR al.error_message IS NOT NULL)
               ORDER BY al.id DESC LIMIT %s""", (limit,)
        ).fetchall())
        errors.sort(key=lambda row: row["timestamp"] or "", reverse=True)
        errors = errors[:limit]
        return {"summary": summary, "recent": recent, "errors": errors}


def fetch_merchant_outlets_from_db() -> List[Any]:
    from core.sheets import MerchantOutlet
    stores = _store_query()
    outlets = []
    for s in stores:
        outlets.append(MerchantOutlet(
            kepemilikan=s.get("kepemilikan") or "VB",
            paket=s.get("paket", "3 Bulan"),
            tanggal_mulai_layanan=s.get("tanggal_mulai_layanan", ""),
            tanggal_berakhir_layanan=s.get("tanggal_berakhir_layanan", ""),
            hp=s.get("shopee_phone", ""),
            username=s.get("account_username", "auto7313"),
            password=s.get("shopee_password", ""),
            nama_pemilik=s.get("nama_pemilik", ""),
            nama_portal=s.get("merchant_name", ""),
            merchant_id=str(s.get("store_id", "")),
            store_id=str(s.get("store_id", "")),
            nama_panjang_outlet=s.get("store_name", ""),
            nama_pendek_outlet=s.get("store_name", ""),
            status_utama="On" if s.get("vercel_status") == "ON" else "Off",
            status_aktual=s.get("shopee_status", "UNKNOWN"),
            vercel_link=s.get("vercel_link", ""),
            vercel_password=s.get("vercel_password", ""),
            # The bot-oc decision gate may use only Shopee's fetched schedule.
            # An absent schedule must remain absent and must not fall back to
            # the internal operating-hours table.
            regular_hours=s.get("shopee_regular_hours") or {},
            special_hours=s.get("special_hours", ""),
            timezone=normalize_timezone(s.get("timezone")),
            status_langganan=s.get("subscription_status", "Aktif"),
            penangguhan="Ya" if s.get("is_suspended") else "Tidak",
            pause_until=s.get("pause_until") or "",
            shopee_regular_hours=s.get("shopee_regular_hours") or {},
            schedule_fetch_status=s.get("schedule_fetch_status") or SCHEDULE_FETCH_NOT_FETCHED_YET,
            schedule_fetch_attempted_at=s.get("schedule_fetch_attempted_at") or "",
            schedule_fetch_succeeded_at=s.get("schedule_fetch_succeeded_at") or "",
            schedule_fetch_error=s.get("schedule_fetch_error") or "",
        ))
    return outlets


def delete_store(store_id: str) -> bool:
    with get_db_connection() as conn:
        outlet = conn.execute("SELECT id, merchant_id, portal_id FROM outlets WHERE store_id=%s", (store_id,)).fetchone()
        if not outlet:
            return False
        oid = outlet["id"]
        mid = outlet["merchant_id"]
        pid = outlet["portal_id"]

        conn.execute("DELETE FROM subscriptions WHERE outlet_id=%s", (oid,))
        conn.execute("DELETE FROM operating_hours WHERE outlet_id=%s", (oid,))
        conn.execute("DELETE FROM outlet_states WHERE outlet_id=%s", (oid,))
        conn.execute("DELETE FROM automation_logs WHERE outlet_id=%s", (oid,))
        conn.execute("DELETE FROM admin_audit_logs WHERE outlet_id=%s", (oid,))
        conn.execute("DELETE FROM outlets WHERE id=%s", (oid,))

        remaining = conn.execute("SELECT COUNT(*) AS cnt FROM outlets WHERE merchant_id=%s", (mid,)).fetchone()
        if remaining and remaining["cnt"] == 0:
            # Remove every Shopee account attached to the merchant's portals
            # before deleting the portals themselves.
            conn.execute("DELETE FROM shopee_accounts WHERE portal_id IN (SELECT id FROM portals WHERE merchant_id=%s)", (mid,))
            conn.execute("DELETE FROM portals WHERE merchant_id=%s", (mid,))
            conn.execute("DELETE FROM bot_merchant_assignments WHERE merchant_id=%s", (mid,))
            conn.execute("DELETE FROM dashboard_accounts WHERE merchant_id=%s", (mid,))
            conn.execute("DELETE FROM merchants WHERE id=%s", (mid,))
        return True


def delete_merchant(nama_pemilik: str) -> bool:
    with get_db_connection() as conn:
        merchant = conn.execute("SELECT id FROM merchants WHERE name=%s", (nama_pemilik,)).fetchone()
        if not merchant:
            return False
        mid = merchant["id"]
        outlets = conn.execute("SELECT id FROM outlets WHERE merchant_id=%s", (mid,)).fetchall()
        for o in outlets:
            oid = o["id"]
            conn.execute("DELETE FROM subscriptions WHERE outlet_id=%s", (oid,))
            conn.execute("DELETE FROM operating_hours WHERE outlet_id=%s", (oid,))
            conn.execute("DELETE FROM outlet_states WHERE outlet_id=%s", (oid,))
            conn.execute("DELETE FROM automation_logs WHERE outlet_id=%s", (oid,))
            conn.execute("DELETE FROM admin_audit_logs WHERE outlet_id=%s", (oid,))
            conn.execute("DELETE FROM outlets WHERE id=%s", (oid,))

        conn.execute("DELETE FROM shopee_accounts WHERE portal_id IN (SELECT id FROM portals WHERE merchant_id=%s)", (mid,))
        conn.execute("DELETE FROM portals WHERE merchant_id=%s", (mid,))
        conn.execute("DELETE FROM bot_merchant_assignments WHERE merchant_id=%s", (mid,))
        conn.execute("DELETE FROM dashboard_accounts WHERE merchant_id=%s", (mid,))
        conn.execute("DELETE FROM merchants WHERE id=%s", (mid,))
        return True


init_state = init_db
