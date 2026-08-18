"""PostgreSQL operational store for the monolith dashboard and bot."""

import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster")
BOT_USERNAME = os.getenv("SHOPEE_BOT_USERNAME", "auto7313")
BOT_PASSWORD = os.getenv("SHOPEE_BOT_PASSWORD", "Auto@7313")


def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db() -> None:
    base_dir = Path(__file__).resolve().parents[2] / "database" / "migrations"
    schema_path = base_dir / "001_initial_schema.sql"
    migration2_path = base_dir / "002_separate_merchant_outlet.sql"
    migration3_path = base_dir / "003_add_google_auth.sql"
    migration4_path = base_dir / "004_add_agency_outlet_status.sql"
    with get_db_connection() as conn:
        conn.execute(schema_path.read_text(encoding="utf-8"))
        if migration2_path.exists():
            conn.execute(migration2_path.read_text(encoding="utf-8"))
        if migration3_path.exists():
            conn.execute(migration3_path.read_text(encoding="utf-8"))
        if migration4_path.exists():
            conn.execute(migration4_path.read_text(encoding="utf-8"))
        # Upgrade databases created by the earlier draft without deleting data.
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS password_plain text")
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS link_slug varchar(255)")
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS dashboard_url text")
        conn.execute("ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS role varchar(20) DEFAULT 'MERCHANT'")
        conn.execute("UPDATE dashboard_accounts SET password_plain='Master@00@' WHERE role='MERCHANT' OR role IS NULL")
        conn.execute("ALTER TABLE dashboard_accounts DROP COLUMN IF EXISTS password_hash")
        conn.execute("ALTER TABLE shopee_accounts ADD COLUMN IF NOT EXISTS password_plain text")
        conn.execute("ALTER TABLE shopee_accounts ADD COLUMN IF NOT EXISTS merchant_id_external varchar(100) DEFAULT ''")
        conn.execute("UPDATE shopee_accounts SET password_plain=COALESCE(password_plain, '') WHERE password_plain IS NULL")
        conn.execute("ALTER TABLE outlets DROP COLUMN IF EXISTS short_name")
        conn.execute("CREATE TABLE IF NOT EXISTS system_settings (key varchar(100) PRIMARY KEY, value text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
        conn.execute("INSERT INTO system_settings (key, value) VALUES ('auto_force_close_enabled', 'false') ON CONFLICT (key) DO NOTHING")
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")
        conn.execute(
            "INSERT INTO dashboard_accounts (username,password_plain,role,is_active) VALUES (%s,%s,'ADMIN',true) ON CONFLICT (username) DO NOTHING",
            (admin_username, admin_password),
        )
        conn.execute("INSERT INTO bot_accounts (username,password_plain,name) VALUES (%s,%s,%s) ON CONFLICT (username) DO UPDATE SET password_plain=EXCLUDED.password_plain,updated_at=now()", (BOT_USERNAME, BOT_PASSWORD, "Bot Satpam Utama"))


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


def get_agency_auto_toggle() -> bool:
    val = get_system_setting("auto_force_close_enabled", "false")
    return val.strip().lower() in ["true", "1", "on"]


def set_agency_auto_toggle(enabled: bool) -> bool:
    return set_system_setting("auto_force_close_enabled", "true" if enabled else "false")


def get_agency_outlet_statuses() -> Dict[str, Dict]:
    """
    Returns all rows from agency_outlet_status as a dict keyed by store_id.
    Each value: { shopee_status, last_checked, last_action }.
    Returns empty dict if table is empty or query fails.
    """
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT store_id, shopee_status, last_checked, last_action "
                "FROM agency_outlet_status"
            ).fetchall()
        return {
            row["store_id"]: {
                "shopee_status": row["shopee_status"],
                "last_checked": row["last_checked"].isoformat() if row["last_checked"] else None,
                "last_action": row["last_action"],
            }
            for row in rows
        }
    except Exception:
        return {}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "mitra").lower()).strip("-") or "mitra"


def _new_link_slug(owner: str) -> str:
    return f"{_slug(owner)}-{secrets.token_urlsafe(16).rstrip('=')[:22]}"


def _context(conn, owner: str, merchant_name: str, dashboard_password: str = "", base_url: str = "", google_email: Optional[str] = None):
    owner_clean = (owner or "Unassigned").strip()
    portal_clean = (merchant_name or "Unknown Merchant").strip()

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


def save_or_update_store(store_id: str, store_name: str, merchant_name: str, account_username: str = "", nama_pemilik: str = "", ownership_type: str = "VB", paket: str = "3 Bulan", tanggal_mulai_layanan: str = "", tanggal_berakhir_layanan: str = "", vercel_link: str = "", vercel_password: str = "", vercel_status: str = "ON", shopee_status: str = "UNKNOWN", subscription_status: str = "Aktif", is_suspended: bool = False, alasan_penangguhan: str = "", pause_until: Optional[str] = None, regular_hours: Optional[Dict] = None, special_hours: str = "", base_url: str = "", google_email: Optional[str] = None, **_ignored) -> Dict:
    with get_db_connection() as conn:
        merchant_id, portal_id, account = _context(conn, nama_pemilik, merchant_name, vercel_password, base_url=base_url, google_email=google_email)
        existing_account = conn.execute("SELECT id FROM shopee_accounts WHERE portal_id=%s AND username=%s", (portal_id, account_username or BOT_USERNAME)).fetchone()
        if existing_account:
            shopee_account_id = existing_account["id"]
            if vercel_password:
                conn.execute("UPDATE shopee_accounts SET password_plain=%s,updated_at=now() WHERE id=%s", (vercel_password or BOT_PASSWORD, shopee_account_id))
        else:
            shopee_account_id = conn.execute("INSERT INTO shopee_accounts (portal_id,merchant_id_external,username,password_plain) VALUES (%s,'',%s,%s) RETURNING id", (portal_id, account_username or BOT_USERNAME, vercel_password or BOT_PASSWORD)).fetchone()["id"]
        outlet = conn.execute("INSERT INTO outlets (merchant_id,portal_id,shopee_account_id,store_id,ownership_type,long_name,special_hours) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (store_id) DO UPDATE SET merchant_id=EXCLUDED.merchant_id,portal_id=EXCLUDED.portal_id,shopee_account_id=EXCLUDED.shopee_account_id,ownership_type=EXCLUDED.ownership_type,long_name=EXCLUDED.long_name,special_hours=EXCLUDED.special_hours,updated_at=now() RETURNING id", (merchant_id, portal_id, shopee_account_id, store_id, ownership_type, store_name or store_id, special_hours)).fetchone()
        outlet_id = outlet["id"]
        conn.execute("INSERT INTO outlet_states (outlet_id,vercel_status,shopee_actual_status,suspension_status,suspension_reason,pause_until) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (outlet_id) DO UPDATE SET shopee_actual_status=EXCLUDED.shopee_actual_status,updated_at=now()", (outlet_id, (vercel_status or "OFF").upper(), (shopee_status or "UNKNOWN").upper(), "SUSPENDED" if is_suspended else "ACTIVE", alasan_penangguhan, pause_until))
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
    if act in ("ACTION_OPEN", "USER_RESUME_STORE", "OPEN_STORE", "OPEN"):
        return "action open"
    elif act in ("ACTION_CLOSE", "USER_PAUSE_STORE", "CLOSE_STORE", "CLOSE", "PAUSE"):
        return "action close"
    elif act in ("NO_CHANGE", "NONE"):
        return "no change"
    else:
        return "no change"


def _store_query(where: str = "", params=()) -> List[Dict]:
    query = """SELECT o.id AS outlet_uuid,o.store_id,o.long_name AS store_name,o.long_name,o.ownership_type AS kepemilikan,o.special_hours,p.name AS merchant_name,p.name AS nama_portal,m.name AS nama_pemilik,m.id AS merchant_id,%s AS account_username,da.username,da.password_plain AS vercel_password,da.dashboard_url AS vercel_link,da.google_email,os.vercel_status,os.shopee_actual_status AS shopee_status,os.suspension_status,(os.suspension_status='SUSPENDED') AS is_suspended,os.suspension_reason AS alasan_penangguhan,os.pause_until::text AS pause_until,os.last_checked_at::text AS last_synced_at,al.action AS last_action_raw,COALESCE(CASE WHEN s.status='ACTIVE' THEN 'Aktif' WHEN s.status='EXPIRED' THEN 'Kedaluwarsa' ELSE s.status END,CASE WHEN s.end_date>=CURRENT_DATE THEN 'Aktif' ELSE 'Kedaluwarsa' END,'Aktif') AS subscription_status,s.start_date::text AS tanggal_mulai_layanan,s.end_date::text AS tanggal_berakhir_layanan,sp.name AS paket FROM outlets o JOIN merchants m ON m.id=o.merchant_id JOIN portals p ON p.id=o.portal_id LEFT JOIN shopee_accounts sa ON sa.id=o.shopee_account_id LEFT JOIN dashboard_accounts da ON da.merchant_id=m.id AND da.role='MERCHANT' LEFT JOIN outlet_states os ON os.outlet_id=o.id LEFT JOIN LATERAL (SELECT action FROM automation_logs WHERE outlet_id=o.id ORDER BY id DESC LIMIT 1) al ON true LEFT JOIN LATERAL (SELECT * FROM subscriptions sx WHERE sx.outlet_id=o.id ORDER BY sx.end_date DESC LIMIT 1) s ON true LEFT JOIN subscription_plans sp ON sp.id=s.plan_id"""
    if where: query += " WHERE " + where
    query += " ORDER BY m.name,p.name,o.store_id"
    with get_db_connection() as conn:
        rows = [dict(row) for row in conn.execute(query, (BOT_USERNAME, *params)).fetchall()]
        if not rows:
            return []
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
        for r in rows:
            r["regular_hours"] = hours_map.get(r["outlet_uuid"], {})
            r["special_hours"] = r.get("special_hours") or ""
            r["last_action"] = format_last_action(r.get("last_action_raw"))
        return rows


def get_all_stores(): return _store_query()
def get_store_by_id(store_id):
    rows = _store_query("o.store_id=%s", (store_id,)); return rows[0] if rows else None
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
    with get_db_connection() as conn: conn.execute("""UPDATE outlet_states os SET vercel_status=CASE WHEN os.suspension_status='SUSPENDED' OR EXISTS (SELECT 1 FROM subscriptions sx WHERE sx.outlet_id=os.outlet_id AND sx.end_date<CURRENT_DATE AND sx.status<>'CANCELLED') THEN 'OFF' ELSE %s END,pause_until=%s,updated_at=now() FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""", (status.upper(), pause_until, store_id))
def admin_set_suspension(store_id, penangguhan, alasan=""):
    suspended = penangguhan.lower() == "ya"
    with get_db_connection() as conn: conn.execute("UPDATE outlet_states os SET suspension_status=%s,suspension_reason=%s,vercel_status=CASE WHEN %s THEN 'OFF' ELSE vercel_status END,updated_at=now() FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s", ("SUSPENDED" if suspended else "ACTIVE", alasan, suspended, store_id))
def admin_renew_subscription(store_id, new_expiry_date):
    with get_db_connection() as conn: conn.execute("UPDATE subscriptions s SET end_date=%s,status='ACTIVE',updated_at=now() FROM outlets o WHERE o.id=s.outlet_id AND o.store_id=%s", (new_expiry_date, store_id))
def admin_edit_outlet(store_id: str, nama_pemilik: Optional[str] = None, nama_portal: Optional[str] = None, nama_panjang_outlet: Optional[str] = None, ownership_type: Optional[str] = None, paket: Optional[str] = None, dashboard_password: Optional[str] = None, google_email: Optional[str] = None) -> bool:
    with get_db_connection() as conn:
        outlet = conn.execute("SELECT id, merchant_id, portal_id FROM outlets WHERE store_id=%s", (store_id,)).fetchone()
        if not outlet:
            return False
        oid = outlet["id"]
        mid = outlet["merchant_id"]
        pid = outlet["portal_id"]
        if nama_panjang_outlet is not None and nama_panjang_outlet.strip():
            conn.execute("UPDATE outlets SET long_name=%s, updated_at=now() WHERE id=%s", (nama_panjang_outlet.strip(), oid))
        if ownership_type is not None and ownership_type.strip():
            conn.execute("UPDATE outlets SET ownership_type=%s, updated_at=now() WHERE id=%s", (ownership_type.strip(), oid))
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
            conn.execute("UPDATE dashboard_accounts SET google_email=%s, updated_at=now() WHERE merchant_id=%s AND role='MERCHANT'", (google_email.strip() or None, mid))
        if paket is not None and paket.strip():
            code = paket.strip().upper().replace(" ", "_")
            if code in {"3_MONTHS", "6_MONTHS", "12_MONTHS"}:
                plan = conn.execute("SELECT id FROM subscription_plans WHERE code=%s", (code,)).fetchone()
                if plan:
                    conn.execute("UPDATE subscriptions SET plan_id=%s, updated_at=now() WHERE outlet_id=%s", (plan["id"], oid))
        return True

def update_shopee_actual_status(store_id, status):
    with get_db_connection() as conn: conn.execute("UPDATE outlet_states os SET shopee_actual_status=%s,updated_at=now() FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s", (status.upper(), store_id))
def record_log(store_id, store_name, action, target_state, reason):
    with get_db_connection() as conn:
        outlet = conn.execute("SELECT id FROM outlets WHERE store_id=%s", (store_id,)).fetchone()
        if not outlet: return
        row = conn.execute("SELECT vercel_status,shopee_actual_status,suspension_status FROM outlet_states WHERE outlet_id=%s", (outlet["id"],)).fetchone() or {}
        conn.execute("INSERT INTO automation_logs (outlet_id,suspension_status,subscription_status,vercel_status_before,shopee_status_before,target_status,action,success,reason) VALUES (%s,%s,'ACTIVE',%s,%s,%s,%s,true,%s)", (outlet["id"], row.get("suspension_status", "ACTIVE"), row.get("vercel_status", "OFF"), row.get("shopee_actual_status", "UNKNOWN"), target_state, action, reason))
        conn.execute("UPDATE outlet_states SET last_action_at=now(), last_checked_at=now(), updated_at=now() WHERE outlet_id=%s", (outlet["id"],))
def get_recent_logs(limit=50, store_ids=None):
    query = """
        SELECT
            al.id,
            al.checked_at::text AS timestamp,
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
            hp="",
            username=s.get("account_username", "auto7313"),
            password="",
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
            regular_hours=s.get("regular_hours", {}),
            special_hours=s.get("special_hours", ""),
            status_langganan=s.get("subscription_status", "Aktif"),
            penangguhan="Ya" if s.get("is_suspended") else "Tidak",
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
