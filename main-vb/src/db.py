"""Database access for the VB patrol service."""

from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config import DATABASE_URL


def connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


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
           WHERE id=%s AND applied_status='PAUSED'
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
           WHERE id=%s AND requested_status IS NOT NULL
           RETURNING id, name, applied_status, requested_by""", (brand_id,)
    ).fetchone()
    if row:
        conn.execute(
            """INSERT INTO admin_audit_logs
               (admin_account_id, vb_brand_id, action, old_value, new_value, reason)
               VALUES (%s, %s, 'VB_CONTROL_STATUS_APPLIED', %s, %s, %s)""",
            (row["requested_by"], row["id"],
             Jsonb({"pending": True}), Jsonb({"applied_status": row["applied_status"]}),
             "Perubahan diterapkan saat brand mendapat giliran patroli"),
        )
    return row


def mark_patrolled(conn, brand_id):
    conn.execute("UPDATE vb_brands SET last_patrolled_at=now(), updated_at=now() WHERE id=%s", (brand_id,))


def create_patrol_run(conn):
    return conn.execute("INSERT INTO vb_patrol_runs DEFAULT VALUES RETURNING id").fetchone()["id"]
