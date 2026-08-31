"""Database access for the VB patrol service."""

from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config import DATABASE_URL, USERNAME, PASSWORD


def connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def apply_all_pending_statuses(conn) -> list[dict[str, Any]]:
    """Apply any pending requested_status to applied_status for all active brands,
    and automatically revert expired timed pauses back to ON.
    """
    # 1. Expire timed pauses that have passed their deadline
    conn.execute("""
        UPDATE vb_brands
        SET requested_status='ON', requested_pause_until=NULL,
            requested_at=now(), updated_at=now()
        WHERE is_active=true
          AND applied_status='PAUSED'
          AND pause_until IS NOT NULL AND pause_until <= now()
          AND requested_status IS NULL
    """)
    # 2. Apply all pending requested_status
    rows = conn.execute("""
        UPDATE vb_brands
        SET applied_status=requested_status,
            pause_until=CASE WHEN requested_status='PAUSED' THEN requested_pause_until ELSE NULL END,
            requested_status=NULL,
            requested_pause_until=NULL,
            requested_at=NULL,
            last_applied_at=now(),
            updated_at=now()
        WHERE is_active=true AND requested_status IS NOT NULL
        RETURNING id, name, applied_status, pause_until, requested_by
    """).fetchall()
    for row in rows:
        conn.execute(
            """INSERT INTO admin_audit_logs
               (admin_account_id, vb_brand_id, action, old_value, new_value, reason)
               VALUES (%s, %s, 'VB_CONTROL_STATUS_APPLIED', %s, %s, %s)""",
            (row.get("requested_by"), row["id"],
             Jsonb({"pending": True}), Jsonb({"applied_status": row["applied_status"]}),
             "Perubahan diterapkan saat brand mendapat giliran patroli"),
        )
    return rows


def sync_expired_user_pauses():
    """Mark expired timed brand pauses ON on patrol turn and apply pending changes."""
    with connection() as conn:
        apply_all_pending_statuses(conn)


def normalize_brand(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def list_brands(conn) -> list[dict[str, Any]]:
    return list(conn.execute(
        """SELECT id, name, applied_status, requested_status, requested_at,
                  pause_until, requested_pause_until
           FROM vb_brands WHERE is_active=true ORDER BY name_normalized"""
    ).fetchall())


def get_brand_outlets(conn, brand_id):
    return list(conn.execute(
        """SELECT o.id AS outlet_id, o.store_id, o.long_name, p.name AS portal_name,
                  sa.username, sa.password_plain, sa.phone,
                  sa.merchant_id_external, os.shopee_actual_status
           FROM vb_brand_outlets bo
           JOIN outlets o ON o.id=bo.outlet_id AND o.is_active=true
           JOIN portals p ON p.id=o.portal_id AND p.is_active=true
           LEFT JOIN shopee_accounts sa ON sa.id=o.shopee_account_id
           LEFT JOIN outlet_states os ON os.outlet_id=o.id
           WHERE bo.vb_brand_id=%s
           ORDER BY p.name, o.store_id""", (brand_id,)
    ).fetchall())


def apply_pending_status(conn, brand_id):
    # Timed brand pauses expire on the next patrol turn. Convert the expired
    # state into the same pending ON transition used by the admin control.
    conn.execute(
        """UPDATE vb_brands
           SET requested_status='ON', requested_pause_until=NULL,
               requested_at=now(), updated_at=now()
           WHERE id=%s AND is_active=true AND applied_status='PAUSED'
             AND pause_until IS NOT NULL AND pause_until <= now()
             AND requested_status IS NULL""",
        (brand_id,),
    )
    row = conn.execute(
        """UPDATE vb_brands
           SET applied_status=requested_status,
               pause_until=CASE WHEN requested_status='PAUSED' THEN requested_pause_until ELSE NULL END,
               requested_status=NULL, requested_pause_until=NULL,
               requested_at=NULL, last_applied_at=now(), updated_at=now()
           WHERE id=%s AND is_active=true AND requested_status IS NOT NULL
           RETURNING id, name, applied_status, pause_until, requested_by""", (brand_id,)
    ).fetchone()
    if row:
        conn.execute(
            """INSERT INTO admin_audit_logs
               (admin_account_id, vb_brand_id, action, old_value, new_value, reason)
               VALUES (%s, %s, 'VB_CONTROL_STATUS_APPLIED', %s, %s, %s)""",
            (row.get("requested_by"), row["id"],
             Jsonb({"pending": True}), Jsonb({"applied_status": row["applied_status"]}),
             "Perubahan diterapkan saat brand mendapat giliran patroli"),
        )
    return row


def mark_patrolled(conn, brand_id):
    conn.execute("UPDATE vb_brands SET last_patrolled_at=now(), updated_at=now() WHERE id=%s", (brand_id,))


def create_patrol_run(conn):
    return conn.execute("INSERT INTO vb_patrol_runs DEFAULT VALUES RETURNING id").fetchone()["id"]


def fetch_merchant_outlets_from_db() -> list[Any]:
    """Return only active Virtual Brand outlets for the copied worker engine.

    The admin Virtual Brand toggle is the target-state source of truth.  The
    spreadsheet is intentionally not read here; it is import-only.
    """
    from core.sheets import MerchantOutlet

    query = """
        SELECT b.name AS brand_name,
               COALESCE(b.requested_status, b.applied_status) AS effective_status,
               COALESCE(b.requested_pause_until, b.pause_until)::text AS brand_pause_until,
               o.store_id, o.long_name, p.name AS portal_name,
               sa.username, sa.password_plain, sa.phone, sa.merchant_id_external,
               os.shopee_actual_status, os.shopee_regular_hours, os.timezone
        FROM vb_brand_outlets bo
        JOIN vb_brands b ON b.id = bo.vb_brand_id AND b.is_active = true
        JOIN outlets o ON o.id = bo.outlet_id AND o.is_active = true
        JOIN portals p ON p.id = o.portal_id AND p.is_active = true
        LEFT JOIN shopee_accounts sa ON sa.id = o.shopee_account_id
        LEFT JOIN outlet_states os ON os.outlet_id = o.id
        WHERE o.store_id ~ '^[0-9]+$' AND p.name !~* '^(status|status import|import status)$'
        ORDER BY b.name, p.name, o.store_id
    """
    with connection() as conn:
        apply_all_pending_statuses(conn)
        rows = conn.execute(query).fetchall()

    # A Store ID may be linked to more than one active brand. Patrol it once
    # per portal and use the most restrictive desired state to avoid duplicate
    # actions or an ON row overriding an OFF row.
    unique_rows = {}
    for row in rows:
        store_id = str(row.get("store_id") or "").strip()
        existing = unique_rows.get(store_id)
        if existing is None:
            unique_rows[store_id] = row
            continue
        if str(row.get("effective_status") or "ON").upper() != "ON":
            existing["effective_status"] = row.get("effective_status")
            existing["brand_pause_until"] = row.get("brand_pause_until")
    rows = list(unique_rows.values())

    outlets = []
    for row in rows:
        store_id = str(row.get("store_id") or "").strip()
        portal_name = str(row.get("portal_name") or "").strip()
        if not store_id.isdigit() or portal_name.casefold() in {"status", "status import", "import status"}:
            continue
        actual = (row.get("shopee_actual_status") or "UNKNOWN").upper()
        if actual == "OFF":
            actual = "CLOSED"
        effective = (row.get("effective_status") or "ON").upper()
        target = "ON" if effective == "ON" else "OFF"
        outlets.append(MerchantOutlet(
            nama_pemilik=row.get("brand_name") or "Virtual Brand",
            kepemilikan="VB",
            paket="",
            tanggal_mulai_layanan="",
            tanggal_berakhir_layanan="",
            username=USERNAME,
            password=PASSWORD,
            hp=row.get("phone") or "",
            nama_portal=row.get("portal_name") or "",
            merchant_id=str(row.get("merchant_id_external") or ""),
            store_id=str(row.get("store_id") or ""),
            nama_panjang_outlet=row.get("long_name") or str(row.get("store_id") or ""),
            nama_pendek_outlet=row.get("long_name") or "",
            status_utama=target,
            status_aktual=actual,
            regular_hours=row.get("shopee_regular_hours") or {},
            shopee_regular_hours=row.get("shopee_regular_hours") or {},
            timezone=row.get("timezone") or "Asia/Jakarta",
            status_langganan="Aktif",
            penangguhan="Tidak",
            alasan_penangguhan="",
            pause_until=row.get("brand_pause_until") or "",
        ))
    return outlets


def update_shopee_regular_hours(store_id: str, regular_hours: dict) -> None:
    with connection() as conn:
        conn.execute(
            """UPDATE outlet_states os SET shopee_regular_hours=%s,
               last_checked_at=now(), updated_at=now()
               FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (Jsonb(regular_hours), store_id),
        )


def update_shopee_actual_status(store_id: str, status: str) -> None:
    # outlet_states deliberately stores OFF for Shopee CLOSED because CLOSED
    # is not one of the column's allowed persisted values.
    persisted = "OFF" if str(status).upper() in {"CLOSED", "CLOSE"} else str(status).upper()
    if persisted not in {"ON", "PAUSE", "OFF", "UNKNOWN"}:
        persisted = "UNKNOWN"
    with connection() as conn:
        conn.execute(
            """UPDATE outlet_states os SET shopee_actual_status=%s,
               last_checked_at=now(), updated_at=now()
               FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (persisted, store_id),
        )


def update_outlet_timezone(store_id: str, timezone: str) -> None:
    """Persist Shopee's outlet timezone, falling back safely to WIB."""
    from core.timezones import normalize_timezone

    with connection() as conn:
        conn.execute(
            """UPDATE outlet_states os SET timezone=%s, updated_at=now()
               FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (normalize_timezone(timezone), store_id),
        )


def record_log(store_id, store_name, action, target_state, reason, success=True, error_message=None, mode="VB"):
    """Write copied-worker actions as VB logs without mixing regular bot logs."""
    with connection() as conn:
        outlet = conn.execute(
            "SELECT id FROM outlets WHERE store_id=%s", (store_id,)
        ).fetchone()
        if not outlet:
            return
        state = conn.execute(
            "SELECT vercel_status, shopee_actual_status FROM outlet_states WHERE outlet_id=%s",
            (outlet["id"],),
        ).fetchone() or {}
        brand = conn.execute(
            """SELECT bo.vb_brand_id FROM vb_brand_outlets bo
               WHERE bo.outlet_id=%s LIMIT 1""", (outlet["id"],)
        ).fetchone()
        conn.execute(
            """INSERT INTO automation_logs
               (outlet_id, mode, vb_brand_id, suspension_status, subscription_status,
                vercel_status_before, shopee_status_before, target_status, action,
                success, error_message, reason)
               VALUES (%s,%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s,%s,%s)""",
            (outlet["id"], mode, brand["vb_brand_id"] if brand else None,
             "ACTIVE", state.get("vercel_status", "OFF"),
             state.get("shopee_actual_status", "UNKNOWN"), target_state, action,
             success, error_message, reason),
        )
        conn.execute(
            "UPDATE outlet_states SET last_action_at=now(), last_checked_at=now(), updated_at=now() WHERE outlet_id=%s",
            (outlet["id"],),
        )
