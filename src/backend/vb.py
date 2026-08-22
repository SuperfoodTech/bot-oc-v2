"""Virtual Brand database operations for the authenticated admin backend."""

from __future__ import annotations

import csv
import io
from typing import Any

import requests
from psycopg.types.json import Jsonb

from backend.db import get_db_connection

VB_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSTEPFClRQogVXYHNo3PRN4m91wHoKHSpS6Dg5Ofj08JFZdoCS9apvvh3C2OTVpqpebFk6xhaQs6ljY/"
    "pub?gid=2099001096&single=true&output=csv"
)
VB_OWNER_NAME = "VB"
VB_ACCOUNT_USERNAME = "auto7313"


def normalize_brand(name: str) -> str:
    return " ".join((name or "").strip().split()).casefold()


def list_brands() -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = list(conn.execute(
            """SELECT b.id, b.name, b.applied_status, b.requested_status,
                      b.requested_at, b.last_applied_at, b.last_patrolled_at,
                      COUNT(bo.outlet_id)::int AS outlet_count,
                      COUNT(DISTINCT o.portal_id)::int AS merchant_count
               FROM vb_brands b
               LEFT JOIN vb_brand_outlets bo ON bo.vb_brand_id=b.id
               LEFT JOIN outlets o ON o.id=bo.outlet_id
               WHERE b.is_active=true
               GROUP BY b.id
               ORDER BY b.name_normalized"""
        ).fetchall())
        return rows


def brand_detail(brand_id: str) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        brand = conn.execute(
            "SELECT id, name, applied_status, requested_status, requested_at, last_applied_at, last_patrolled_at FROM vb_brands WHERE id=%s AND is_active=true",
            (brand_id,),
        ).fetchone()
        if not brand:
            return None
        stores = list(conn.execute(
            """SELECT o.store_id, o.long_name, p.name AS merchant_name,
                      os.shopee_actual_status
               FROM vb_brand_outlets bo
               JOIN outlets o ON o.id=bo.outlet_id
               JOIN portals p ON p.id=o.portal_id
               LEFT JOIN outlet_states os ON os.outlet_id=o.id
               WHERE bo.vb_brand_id=%s
               ORDER BY p.name, o.store_id""", (brand_id,)
        ).fetchall())
        return {**brand, "outlets": stores}


def request_status(brand_id: str, status: str, admin_id: str) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """UPDATE vb_brands
                   SET requested_status=%s, requested_at=now(), requested_by=%s, updated_at=now()
                   WHERE id=%s AND is_active=true
                   RETURNING id, name, applied_status, requested_status, requested_at""",
                (status, admin_id, brand_id),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """INSERT INTO admin_audit_logs
                   (admin_account_id, vb_brand_id, action, old_value, new_value, reason)
                   VALUES (%s, %s, 'VB_CONTROL_STATUS_REQUESTED', %s, %s, %s)""",
                (admin_id, brand_id,
                 Jsonb({"applied_status": row["applied_status"]}),
                 Jsonb({"requested_status": row["requested_status"]}),
                 "Perubahan menunggu giliran brand pada putaran patroli berikutnya"),
            )
            return row


def _parse_matrix(content: str) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return []
    headers = rows[0]
    matrix = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not row[0].strip():
            continue
        stores = []
        for col_index, value in enumerate(row[1:], start=1):
            if value.strip():
                stores.append({
                    "store_id": value.strip(),
                    "source_column": headers[col_index].strip() if col_index < len(headers) else "",
                })
        matrix.append({"row_number": row_number, "brand": row[0].strip(), "stores": stores})
    return matrix


def import_sheet(admin_id: str) -> dict[str, Any]:
    response = requests.get(VB_SHEET_URL, timeout=20)
    response.raise_for_status()
    matrix = _parse_matrix(response.content.decode("utf-8"))
    brands_created = 0
    outlets_linked = 0
    outlets_created = 0
    portal_mismatches: list[dict[str, Any]] = []
    missing_store_ids: list[dict[str, Any]] = []
    with get_db_connection() as conn:
        with conn.transaction():
            owner = conn.execute("SELECT id FROM merchants WHERE name=%s", (VB_OWNER_NAME,)).fetchone()
            if not owner:
                owner = conn.execute("INSERT INTO merchants (name) VALUES (%s) RETURNING id", (VB_OWNER_NAME,)).fetchone()
            owner_id = owner["id"]
            for item in matrix:
                brand = conn.execute(
                    """INSERT INTO vb_brands (name, name_normalized)
                       VALUES (%s, %s)
                       ON CONFLICT (name_normalized) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                       RETURNING id, (xmax = 0) AS inserted""",
                    (item["brand"], normalize_brand(item["brand"])),
                ).fetchone()
                if brand["inserted"]:
                    brands_created += 1
                for store in item["stores"]:
                    outlet = conn.execute(
                        "SELECT id FROM outlets WHERE store_id=%s AND is_active=true",
                        (store["store_id"],),
                    ).fetchone()
                    if not outlet:
                        portal = conn.execute(
                            """INSERT INTO portals (merchant_id, name)
                               VALUES (%s, %s)
                               ON CONFLICT (merchant_id, name) DO UPDATE SET updated_at=now()
                               RETURNING id""",
                            (owner_id, store["source_column"] or "Unknown Merchant"),
                        ).fetchone()
                        account = conn.execute(
                            """INSERT INTO shopee_accounts (portal_id, merchant_id_external, username, password_plain)
                               VALUES (%s, '', %s, '')
                               ON CONFLICT (portal_id, username) DO UPDATE SET updated_at=now()
                               RETURNING id""",
                            (portal["id"], VB_ACCOUNT_USERNAME),
                        ).fetchone()
                        outlet = conn.execute(
                            """INSERT INTO outlets
                               (merchant_id, portal_id, shopee_account_id, store_id, long_name, is_active)
                               VALUES (%s, %s, %s, %s, %s, true)
                               RETURNING id""",
                            (owner_id, portal["id"], account["id"], store["store_id"],
                             f"{item['brand']} - {store['store_id']}"),
                        ).fetchone()
                        conn.execute(
                            """INSERT INTO outlet_states
                               (outlet_id, vercel_status, shopee_actual_status, suspension_status)
                               VALUES (%s, 'ON', 'UNKNOWN', 'ACTIVE')
                               ON CONFLICT (outlet_id) DO NOTHING""",
                            (outlet["id"],),
                        )
                        outlets_created += 1
                    else:
                        current = conn.execute(
                            "SELECT p.name FROM outlets o JOIN portals p ON p.id=o.portal_id WHERE o.id=%s",
                            (outlet["id"],),
                        ).fetchone()
                        if current and current["name"] != store["source_column"]:
                            portal_mismatches.append({"brand": item["brand"], "store_id": store["store_id"], "sheet_portal": store["source_column"], "database_portal": current["name"]})
                    conn.execute(
                        """INSERT INTO vb_brand_outlets (vb_brand_id, outlet_id, source_column)
                           VALUES (%s, %s, %s)
                           ON CONFLICT (vb_brand_id, outlet_id)
                           DO UPDATE SET source_column=EXCLUDED.source_column""",
                        (brand["id"], outlet["id"], store["source_column"]),
                    )
                    outlets_linked += 1
            conn.execute(
                """INSERT INTO admin_audit_logs (admin_account_id, action, new_value, reason)
                   VALUES (%s, 'VB_IMPORT', %s, %s)""",
                (admin_id, Jsonb({"brands_seen": len(matrix), "brands_created": brands_created, "outlets_created": outlets_created, "outlets_linked": outlets_linked}),
                 "Import matrix Virtual Brand dari Google Sheet"),
            )
    return {
        "brands_seen": len(matrix),
        "brands_created": brands_created,
        "outlets_created": outlets_created,
        "outlets_linked": outlets_linked,
        "missing_store_ids": missing_store_ids,
        "portal_mismatches": portal_mismatches,
    }
