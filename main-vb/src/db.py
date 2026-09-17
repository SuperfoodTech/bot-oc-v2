"""Database access for the VB patrol service."""

from __future__ import annotations

import re
import threading
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config import DATABASE_URL, USERNAME, PASSWORD

SCHEDULE_FETCH_NOT_FETCHED_YET = "NOT_FETCHED_YET"
SCHEDULE_FETCH_RETRYING = "FETCH_RETRYING"
SCHEDULE_FETCH_EMPTY = "FETCHED_EMPTY"
SCHEDULE_FETCH_READY = "READY"


def connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_state() -> None:
    """Initialize state for VB daemon (no-op since database schema is initialized by central backend)."""
    pass



_PENDING_BRAND_ACTIONS: dict[str, list[dict]] = {}
_BRAND_TOGGLED_IDS: set[str] = set()
_PENDING_LOCK = threading.Lock()


def _clean_schedule_fetch_error(value) -> str | None:
    raw_value = str(value or "").strip()
    return raw_value or None


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
        with _PENDING_LOCK:
            _BRAND_TOGGLED_IDS.add(str(row["id"]))
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
        with _PENDING_LOCK:
            _BRAND_TOGGLED_IDS.add(str(row["id"]))
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
               os.shopee_actual_status, os.shopee_regular_hours, os.shopee_special_hours, os.timezone,
               os.schedule_fetch_status,
               os.schedule_fetch_attempted_at::text AS schedule_fetch_attempted_at,
               os.schedule_fetch_succeeded_at::text AS schedule_fetch_succeeded_at,
               COALESCE(os.schedule_fetch_error, '') AS schedule_fetch_error
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
            nama_portal=portal_name,
            merchant_id=str(row.get("merchant_id_external") or ""),
            store_id=store_id,
            nama_panjang_outlet=row.get("long_name") or str(row.get("store_id") or ""),
            nama_pendek_outlet=row.get("long_name") or "",
            status_utama=target,
            status_aktual=actual,
            regular_hours=row.get("shopee_regular_hours") or {},
            shopee_regular_hours=row.get("shopee_regular_hours") or {},
            shopee_special_hours=row.get("shopee_special_hours") or [],
            timezone=row.get("timezone") or "Asia/Jakarta",
            status_langganan="Aktif",
            penangguhan="Tidak",
            alasan_penangguhan="",
            pause_until=row.get("brand_pause_until") or "",
            schedule_fetch_status=row.get("schedule_fetch_status") or SCHEDULE_FETCH_NOT_FETCHED_YET,
            schedule_fetch_attempted_at=row.get("schedule_fetch_attempted_at") or "",
            schedule_fetch_succeeded_at=row.get("schedule_fetch_succeeded_at") or "",
            schedule_fetch_error=row.get("schedule_fetch_error") or "",
        ))
    return outlets


def update_shopee_regular_hours(store_id: str, regular_hours: dict) -> None:
    from backend.db import normalize_shopee_regular_hours

    normalized_hours = normalize_shopee_regular_hours(regular_hours)
    if not any((normalized_hours or {}).values()):
        mark_schedule_fetch_empty(store_id)
        return
    with connection() as conn:
        conn.execute(
            """UPDATE outlet_states os SET shopee_regular_hours=%s,
               schedule_fetch_status=%s,
               schedule_fetch_attempted_at=now(),
               schedule_fetch_succeeded_at=now(),
               schedule_fetch_error=NULL,
               last_checked_at=now(), updated_at=now()
               FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (Jsonb(normalized_hours), SCHEDULE_FETCH_READY, store_id),
        )


def update_shopee_special_hours(store_id: str, special_hours: Any) -> None:
    payload = special_hours if isinstance(special_hours, list) else (special_hours.get("special_hours", []) if isinstance(special_hours, dict) else [])
    with connection() as conn:
        conn.execute(
            """UPDATE outlet_states os SET shopee_special_hours=%s,
               last_checked_at=now(), updated_at=now()
               FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (Jsonb(payload), store_id),
        )



def mark_schedule_fetch_empty(store_id: str) -> None:
    with connection() as conn:
        conn.execute(
            """UPDATE outlet_states os SET shopee_regular_hours=%s,
               schedule_fetch_status=%s,
               schedule_fetch_attempted_at=now(),
               schedule_fetch_succeeded_at=now(),
               schedule_fetch_error=NULL,
               last_checked_at=now(), updated_at=now()
               FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (Jsonb({}), SCHEDULE_FETCH_EMPTY, store_id),
        )


def mark_schedule_fetch_retry(store_id: str, error_message: str | None) -> None:
    error_text = _clean_schedule_fetch_error(error_message) or "Bot belum berhasil fetch jadwal Shopee."
    with connection() as conn:
        conn.execute(
            """UPDATE outlet_states os SET schedule_fetch_status=%s,
               schedule_fetch_attempted_at=now(),
               schedule_fetch_error=%s,
               last_checked_at=now(), updated_at=now()
               FROM outlets o WHERE o.id=os.outlet_id AND o.store_id=%s""",
            (SCHEDULE_FETCH_RETRYING, error_text, store_id),
        )


def update_shopee_actual_status(store_id: str, status: str) -> None:
    normalized = str(status or "").strip().upper()
    if normalized in {"ON", "OPEN"}:
        persisted = "ON"
    elif normalized == "PAUSE":
        persisted = "PAUSE"
    elif normalized in {"OFF", "CLOSED", "CLOSE"}:
        persisted = "CLOSED"
    else:
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


def update_outlet_name(store_id: str, store_name: str) -> None:
    """Persist Shopee's actual store name into outlets.long_name."""
    name = (store_name or "").strip()[:255]
    if not name:
        return
    with connection() as conn:
        conn.execute(
            """UPDATE outlets SET long_name=%s, updated_at=now()
               WHERE store_id=%s AND (long_name IS NULL OR long_name <> %s)""",
            (name, str(store_id), name),
        )


def _record_pending_brand_action(brand_id: str, store_id: str, store_name: str, action: str, target_state: str, success: bool, error_message: str | None):
    if not brand_id:
        return
    with _PENDING_LOCK:
        if brand_id not in _PENDING_BRAND_ACTIONS:
            _PENDING_BRAND_ACTIONS[brand_id] = []
        _PENDING_BRAND_ACTIONS[brand_id].append({
            "store_id": str(store_id),
            "store_name": store_name,
            "action": action,
            "target_state": target_state,
            "success": success,
            "error_message": error_message,
        })


def get_pending_brand_ids() -> list[str]:
    """Mengembalikan daftar brand_id yang sedang memiliki aksi tertunda di buffer notifikasi."""
    with _PENDING_LOCK:
        return list(_PENDING_BRAND_ACTIONS.keys())


def get_brand_store_ids(brand_ids: list[str] | set[str]) -> dict[str, set[str]]:
    """Mengembalikan mapping {brand_id: set(store_ids)} untuk seluruh outlet aktif di bawah brand terkait."""
    if not brand_ids:
        return {}
    res = {}
    with connection() as conn:
        rows = conn.execute("""
            SELECT bo.vb_brand_id, o.store_id
            FROM vb_brand_outlets bo
            JOIN outlets o ON o.id = bo.outlet_id
            WHERE bo.vb_brand_id = ANY(%s) AND o.is_active = true
        """, (list(brand_ids),)).fetchall()
        for r in rows:
            bid = str(r["vb_brand_id"])
            if bid not in res:
                res[bid] = set()
            if r["store_id"]:
                res[bid].add(str(r["store_id"]))
    return res


def flush_pending_brand_notifications(brand_ids: list[str] | set[str] | None = None):
    with _PENDING_LOCK:
        if not _PENDING_BRAND_ACTIONS:
            return
        if brand_ids is not None:
            target_ids = set(str(b) for b in brand_ids)
            pending = {bid: list(acts) for bid, acts in _PENDING_BRAND_ACTIONS.items() if bid in target_ids}
            for bid in pending:
                del _PENDING_BRAND_ACTIONS[bid]
            toggled_brands = {bid for bid in _BRAND_TOGGLED_IDS if bid in target_ids}
            for bid in toggled_brands:
                _BRAND_TOGGLED_IDS.discard(bid)
        else:
            pending = dict(_PENDING_BRAND_ACTIONS)
            _PENDING_BRAND_ACTIONS.clear()
            toggled_brands = set(_BRAND_TOGGLED_IDS)
            _BRAND_TOGGLED_IDS.clear()

    if not pending:
        return

    try:
        from core.notifier import send_discord_vb_group_summary
        with connection() as conn:
            for brand_id, actions in pending.items():
                brand = conn.execute(
                    "SELECT id, name, applied_status FROM vb_brands WHERE id=%s", (brand_id,)
                ).fetchone()
                if not brand:
                    continue
                brand_name = brand["name"] or "Virtual Brand Group"
                applied_status = str(brand.get("applied_status") or "ON").upper()

                actions_types = [a["action"] for a in actions if a.get("action")]
                is_open = any(a in ("ACTION_OPEN", "USER_OPEN_STORE") for a in actions_types) or applied_status == "ON"
                summary_action = "ACTION_OPEN" if is_open else "ACTION_CLOSE"

                is_brand_toggle = str(brand_id) in toggled_brands

                if is_brand_toggle:
                    # Mode Brand Toggle: Rekap Kolektif Seluruh Outlet di bawah Brand
                    outlets = conn.execute("""
                        SELECT o.store_id, COALESCE(o.long_name, o.store_id) AS name,
                               os.shopee_actual_status, os.vercel_status
                        FROM vb_brand_outlets bo
                        JOIN outlets o ON o.id = bo.outlet_id AND o.is_active = true
                        LEFT JOIN outlet_states os ON os.outlet_id = o.id
                        WHERE bo.vb_brand_id = %s
                        ORDER BY o.store_id
                    """, (brand_id,)).fetchall()

                    if not outlets:
                        continue

                    success_items = []
                    failed_items = []

                    for out in outlets:
                        st_id = str(out["store_id"])
                        st_name = out["name"] or st_id
                        live_st = str(out.get("shopee_actual_status") or "").upper()

                        failed_record = next((a for a in actions if a["store_id"] == st_id and not a.get("success")), None)

                        if is_open:
                            if (live_st in ("ON", "OPEN") or (out.get("vercel_status") == "ON" and live_st != "PAUSE")) and not failed_record:
                                success_items.append({"name": st_name, "store_id": st_id})
                            else:
                                failed_items.append({"name": st_name, "store_id": st_id})
                        else:
                            if (live_st in ("PAUSE", "CLOSED", "OFF")) and not failed_record:
                                success_items.append({"name": st_name, "store_id": st_id})
                            else:
                                failed_items.append({"name": st_name, "store_id": st_id})

                    send_discord_vb_group_summary(
                        group_name=brand_name,
                        action=summary_action,
                        success_items=success_items,
                        failed_items=failed_items,
                        is_guarding=False,
                    )
                else:
                    # Mode Auto-Guarding Keliling: Tampilkan HANYA outlet yang dieksekusi oleh bot
                    success_items = []
                    failed_items = []

                    for a in actions:
                        st_id = str(a.get("store_id") or "")
                        st_name = a.get("store_name") or st_id
                        if a.get("success"):
                            success_items.append({"name": st_name, "store_id": st_id})
                        else:
                            failed_items.append({"name": st_name, "store_id": st_id})

                    send_discord_vb_group_summary(
                        group_name=brand_name,
                        action=summary_action,
                        success_items=success_items,
                        failed_items=failed_items,
                        is_guarding=True,
                    )
    except Exception as e:
        print(f"[VB DB NOTIFICATION ERROR] Gagal mengirim summary group Discord: {e}")


_flush_pending_brand_notifications = flush_pending_brand_notifications


def record_log(store_id, store_name, action, target_state, reason, success=True, error_message=None, mode="VB"):
    """Write copied-worker actions as VB logs without mixing regular bot logs."""
    if str(store_id).upper() == "SYSTEM":
        return

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

        if brand and brand.get("vb_brand_id") and action in ("ACTION_OPEN", "ACTION_CLOSE", "USER_OPEN_STORE", "USER_PAUSE_STORE"):
            _record_pending_brand_action(
                brand_id=str(brand["vb_brand_id"]),
                store_id=str(store_id),
                store_name=store_name,
                action=action,
                target_state=target_state,
                success=success,
                error_message=error_message,
            )

