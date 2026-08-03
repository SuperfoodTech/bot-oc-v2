"""
db.py
=====
SQLite Database Manager for store state persistence, user authentication, and audit logging.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

DB_PATH = Path(__file__).resolve().parent / "database.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users table (for User Link authentication & ownership)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT UNIQUE,
        nama_pemilik TEXT UNIQUE,
        passcode TEXT,
        link_slug TEXT UNIQUE,
        created_at TEXT
    )
    """)

    # 2. Stores table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stores (
        store_id TEXT PRIMARY KEY,
        store_name TEXT,
        merchant_name TEXT,
        account_username TEXT,
        nama_pemilik TEXT,
        paket TEXT DEFAULT '3 Bulan',
        tanggal_mulai_layanan TEXT,
        tanggal_berakhir_layanan TEXT,
        vercel_link TEXT DEFAULT '',
        vercel_password TEXT DEFAULT '',
        vercel_status TEXT DEFAULT 'ON',
        shopee_status TEXT DEFAULT 'UNKNOWN',
        subscription_status TEXT DEFAULT 'Aktif',
        is_suspended INTEGER DEFAULT 0,
        alasan_penangguhan TEXT DEFAULT '',
        pause_until TEXT,
        last_synced_at TEXT
    )
    """)

    # Ensure columns exist if database file pre-existed
    existing_cols = [r[1] for r in cursor.execute("PRAGMA table_info(stores)").fetchall()]
    new_cols = {
        "nama_pemilik": "TEXT DEFAULT ''",
        "paket": "TEXT DEFAULT '3 Bulan'",
        "tanggal_mulai_layanan": "TEXT DEFAULT ''",
        "tanggal_berakhir_layanan": "TEXT DEFAULT ''",
        "vercel_link": "TEXT DEFAULT ''",
        "vercel_password": "TEXT DEFAULT ''",
        "alasan_penangguhan": "TEXT DEFAULT ''"
    }

    for col, col_type in new_cols.items():
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE stores ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # 3. Audit logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS automation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        store_id TEXT,
        store_name TEXT,
        action TEXT,
        target_state TEXT,
        reason TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_or_update_store(
    store_id: str,
    store_name: str,
    merchant_name: str,
    account_username: str,
    nama_pemilik: str = "",
    paket: str = "3 Bulan",
    tanggal_mulai_layanan: str = "",
    tanggal_berakhir_layanan: str = "",
    vercel_link: str = "",
    vercel_password: str = "",
    vercel_status: str = "ON",
    shopee_status: str = "UNKNOWN",
    subscription_status: str = "Aktif",
    is_suspended: bool = False,
    alasan_penangguhan: str = "",
    pause_until: Optional[str] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO stores (
        store_id, store_name, merchant_name, account_username, nama_pemilik,
        paket, tanggal_mulai_layanan, tanggal_berakhir_layanan, vercel_link, vercel_password,
        vercel_status, shopee_status, subscription_status, is_suspended, alasan_penangguhan, pause_until, last_synced_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(store_id) DO UPDATE SET
        store_name=excluded.store_name,
        merchant_name=excluded.merchant_name,
        account_username=excluded.account_username,
        nama_pemilik=excluded.nama_pemilik,
        paket=excluded.paket,
        tanggal_mulai_layanan=excluded.tanggal_mulai_layanan,
        tanggal_berakhir_layanan=excluded.tanggal_berakhir_layanan,
        vercel_link=excluded.vercel_link,
        vercel_password=excluded.vercel_password,
        shopee_status=excluded.shopee_status,
        subscription_status=excluded.subscription_status,
        is_suspended=excluded.is_suspended,
        alasan_penangguhan=excluded.alasan_penangguhan,
        last_synced_at=excluded.last_synced_at
    """, (
        store_id, store_name, merchant_name, account_username, nama_pemilik,
        paket, tanggal_mulai_layanan, tanggal_berakhir_layanan, vercel_link, vercel_password,
        vercel_status, shopee_status, subscription_status, 1 if is_suspended else 0,
        alasan_penangguhan, pause_until, now_str
    ))

    conn.commit()
    conn.close()


# ── ADMIN DATABASE OPERATIONS ─────────────────────────────────────────────────

def admin_get_all_users_with_stores() -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM stores ORDER BY nama_pemilik ASC, store_id ASC")
    stores = [dict(r) for r in cursor.fetchall()]

    # Group stores by nama_pemilik
    users_map = {}
    for s in stores:
        pemilik = s["nama_pemilik"] or "Unassigned"
        if pemilik not in users_map:
            users_map[pemilik] = {
                "nama_pemilik": pemilik,
                "total_outlets": 0,
                "outlets": []
            }
        users_map[pemilik]["outlets"].append(s)
        users_map[pemilik]["total_outlets"] += 1

    conn.close()
    return list(users_map.values())


def admin_generate_user_link(nama_pemilik: str, passcode: Optional[str] = None) -> Dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    slug = nama_pemilik.lower().replace(" ", "-") + "-" + str(uuid.uuid4())[:6]
    pass_code = passcode or "Master@00@"

    cursor.execute("""
    INSERT INTO users (user_id, nama_pemilik, passcode, link_slug, created_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(nama_pemilik) DO UPDATE SET
        passcode=excluded.passcode,
        link_slug=excluded.link_slug
    """, (str(uuid.uuid4()), nama_pemilik, pass_code, slug, now_str))

    conn.commit()
    conn.close()

    return {
        "nama_pemilik": nama_pemilik,
        "passcode": pass_code,
        "link_slug": slug,
        "full_url": f"https://foodmaster-oc.vercel.app/mitra/{slug}"
    }


def admin_set_suspension(store_id: str, penangguhan: str, alasan: str = ""):
    conn = get_db_connection()
    cursor = conn.cursor()
    is_sus = 1 if penangguhan.lower() == "ya" else 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    UPDATE stores
    SET is_suspended = ?, alasan_penangguhan = ?, last_synced_at = ?
    WHERE store_id = ?
    """, (is_sus, alasan, now_str, store_id))

    conn.commit()
    conn.close()


def admin_renew_subscription(store_id: str, new_expiry_date: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    UPDATE stores
    SET tanggal_berakhir_layanan = ?, subscription_status = 'Aktif', last_synced_at = ?
    WHERE store_id = ?
    """, (new_expiry_date, now_str, store_id))

    conn.commit()
    conn.close()


# ── USER DATABASE OPERATIONS ──────────────────────────────────────────────────

def user_authenticate(passcode: str) -> Optional[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check in users table or stores
    cursor.execute("SELECT * FROM users WHERE passcode = ?", (passcode,))
    user_row = cursor.fetchone()

    if user_row:
        conn.close()
        return dict(user_row)

    # Fallback check by default passcode Master@00@
    if passcode in ("Master@00@", "Auto@7313"):
        conn.close()
        return {"nama_pemilik": "Fando", "passcode": passcode, "link_slug": "fando-demo"}

    conn.close()
    return None


def user_get_outlets(nama_pemilik: str) -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stores WHERE nama_pemilik = ? OR nama_pemilik LIKE ? ORDER BY store_id ASC", (nama_pemilik, f"%{nama_pemilik}%"))
    rows = cursor.fetchall()
    conn.close()
    
    # If empty, return all stores for demo user
    if not rows:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stores ORDER BY store_id ASC LIMIT 4")
        rows = cursor.fetchall()
        conn.close()
        
    return [dict(r) for r in rows]


def update_vercel_toggle(store_id: str, status: str, pause_until: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    UPDATE stores
    SET vercel_status = ?, pause_until = ?, last_synced_at = ?
    WHERE store_id = ?
    """, (status, pause_until, now_str, store_id))

    conn.commit()
    conn.close()


def record_log(store_id: str, store_name: str, action: str, target_state: str, reason: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO automation_logs (timestamp, store_id, store_name, action, target_state, reason)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (now_str, store_id, store_name, action, target_state, reason))

    conn.commit()
    conn.close()


def get_all_stores() -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stores ORDER BY store_id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_store_by_id(store_id: str) -> Optional[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stores WHERE store_id = ?", (store_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_logs(limit: int = 50, store_ids: Optional[List[str]] = None) -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if store_ids:
        placeholders = ",".join(["?"] * len(store_ids))
        cursor.execute(f"SELECT * FROM automation_logs WHERE store_id IN ({placeholders}) ORDER BY id DESC LIMIT ?", (*store_ids, limit))
    else:
        cursor.execute("SELECT * FROM automation_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
