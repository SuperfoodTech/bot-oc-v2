"""Virtual Brand database operations for the authenticated admin backend."""

from __future__ import annotations

import csv
import io
from typing import Any

import requests
from psycopg.types.json import Jsonb

from backend.db import derive_outlet_runtime_state, get_db_connection, normalize_shopee_regular_hours
from core.timezones import normalize_timezone

VB_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSsAq8JmDfGI8KY7aSCRpzC2EaQARkK1OvhWrll7g3qlxFMIcwtDpAF-Wxf4aQnGET4eCmncjdEgre5/"
    "pub?gid=935753758&single=true&output=csv"
)
VB_OWNER_NAME = "VB"
VB_ACCOUNT_USERNAME = "auto7313"

PORTAL_NAME_MAP = {
    "doeat": "Gurame Bakar, Do Eat",
    "do eat": "Gurame Bakar, Do Eat",
    "gurame bakar, do eat": "Gurame Bakar, Do Eat",
    "superfood": "SuperFood",
    "wonderfood": "WonderFood",
    "lokarasa": "LOKARASA",
}


def normalize_portal_name(raw_portal: str) -> str:
    clean = " ".join((raw_portal or "").strip().split())
    return PORTAL_NAME_MAP.get(clean.casefold(), clean)


def _store_control_map(conn) -> dict[str, dict[str, Any]]:
    """Return one conservative desired state for each Store ID across brands."""
    rows = conn.execute(
        """SELECT o.store_id,
                  COUNT(*) AS brand_count,
                  BOOL_AND(COALESCE(b.requested_status, b.applied_status, 'ON')='ON') AS all_on
           FROM vb_brand_outlets bo
           JOIN vb_brands b ON b.id=bo.vb_brand_id AND b.is_active=true
           JOIN outlets o ON o.id=bo.outlet_id AND o.is_active=true
           GROUP BY o.store_id"""
    ).fetchall()
    return {
        str(row["store_id"]): {
            "status": "ON" if row["all_on"] else "OFF",
            "brand_count": int(row["brand_count"] or 0),
        }
        for row in rows
    }


import re


def normalize_brand(name: str) -> str:
    return " ".join((name or "").strip().split()).casefold()


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text or "").strip().lower()
    return re.sub(r"[-\s]+", "-", slug) or "brand"


def pick_pause_reference_outlet(outlets: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    normalized_outlets: list[dict[str, Any]] = []
    for outlet in outlets or []:
        candidate = dict(outlet)
        candidate["shopee_regular_hours"] = normalize_shopee_regular_hours(candidate.get("shopee_regular_hours"))
        candidate["timezone"] = normalize_timezone(candidate.get("timezone"))
        normalized_outlets.append(candidate)
    if not normalized_outlets:
        return None
    for candidate in normalized_outlets:
        if any((candidate.get("shopee_regular_hours") or {}).values()):
            return candidate
    return normalized_outlets[0]


def list_brands() -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        store_controls = _store_control_map(conn)
        rows = list(conn.execute(
            """SELECT b.id, b.name, b.applied_status, b.requested_status,
                      b.requested_at, b.pause_until, b.requested_pause_until,
                      b.last_applied_at, b.last_patrolled_at,
                      COALESCE(b.owner_name, 'VB') AS owner_name,
                      COALESCE(b.owner_slug, '') AS owner_slug
               FROM vb_brands b
               WHERE b.is_active=true
               ORDER BY b.owner_name, b.name_normalized"""
        ).fetchall())
        for row in rows:
            row["slug"] = slugify(row["name"])
            if not row.get("owner_slug"):
                row["owner_slug"] = slugify(row["owner_name"])
            stores = list(conn.execute(
                """SELECT o.store_id, o.long_name, p.name AS merchant_name,
                          os.shopee_actual_status, os.shopee_regular_hours, os.shopee_special_hours, os.timezone,
                          os.schedule_fetch_status,
                          os.schedule_fetch_attempted_at::text AS schedule_fetch_attempted_at,
                          os.schedule_fetch_succeeded_at::text AS schedule_fetch_succeeded_at,
                          COALESCE(os.schedule_fetch_error, '') AS schedule_fetch_error
                   FROM vb_brand_outlets bo
                   JOIN outlets o ON o.id=bo.outlet_id AND o.is_active=true
                   JOIN portals p ON p.id=o.portal_id AND p.is_active=true
                   LEFT JOIN outlet_states os ON os.outlet_id=o.id
                   WHERE bo.vb_brand_id=%s
                     AND o.store_id ~ '^[0-9]+$'
                     AND p.name !~* '^(status|status import|import status)$'
                   ORDER BY p.name, o.store_id""",
                (row["id"],),
            ).fetchall())
            for store in stores:
                control = store_controls.get(str(store["store_id"]), {})
                effective_status = control.get("status", "ON")
                store["shopee_regular_hours"] = normalize_shopee_regular_hours(store.get("shopee_regular_hours"))
                store["shopee_special_hours"] = store.get("shopee_special_hours") or []
                store["timezone"] = normalize_timezone(store.get("timezone"))
                store["shopee_status"] = store.get("shopee_actual_status") or "UNKNOWN"
                store["vercel_status"] = "ON" if effective_status == "ON" else "OFF"
                store["duplicate_brand_count"] = control.get("brand_count", 1)
                effective_brand_status = row.get("requested_status") or row.get("applied_status") or "ON"
                store["pause_until"] = (row.get("requested_pause_until") or row.get("pause_until")) if effective_brand_status == "PAUSED" else None
                store.update(derive_outlet_runtime_state(store))
            row["outlets"] = stores
            row["outlet_count"] = len(stores)
            row["merchant_count"] = len({s["merchant_name"] for s in stores if s.get("merchant_name")})
        return rows


def brand_detail(brand_id: str) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        store_controls = _store_control_map(conn)
        brand = conn.execute(
            "SELECT id, name, applied_status, requested_status, requested_at, pause_until, requested_pause_until, last_applied_at, last_patrolled_at FROM vb_brands WHERE id=%s AND is_active=true",
            (brand_id,),
        ).fetchone()
        if not brand:
            return None
        stores = list(conn.execute(
            """SELECT o.store_id, o.long_name, p.name AS merchant_name,
                      os.shopee_actual_status, os.shopee_regular_hours, os.shopee_special_hours, os.timezone,
                      os.schedule_fetch_status,
                      os.schedule_fetch_attempted_at::text AS schedule_fetch_attempted_at,
                      os.schedule_fetch_succeeded_at::text AS schedule_fetch_succeeded_at,
                      COALESCE(os.schedule_fetch_error, '') AS schedule_fetch_error
               FROM vb_brand_outlets bo
               JOIN outlets o ON o.id=bo.outlet_id AND o.is_active=true
               JOIN portals p ON p.id=o.portal_id AND p.is_active=true
               LEFT JOIN outlet_states os ON os.outlet_id=o.id
               WHERE bo.vb_brand_id=%s
                 AND o.store_id ~ '^[0-9]+$'
                 AND p.name !~* '^(status|status import|import status)$'
               ORDER BY p.name, o.store_id""", (brand_id,)
        ).fetchall())
        for store in stores:
            control = store_controls.get(str(store["store_id"]), {})
            effective_status = control.get("status", "ON")
            store["shopee_regular_hours"] = normalize_shopee_regular_hours(store.get("shopee_regular_hours"))
            store["shopee_special_hours"] = store.get("shopee_special_hours") or []
            store["timezone"] = normalize_timezone(store.get("timezone"))
            effective_brand_status = brand.get("requested_status") or brand.get("applied_status") or "ON"
            store["pause_until"] = (brand.get("requested_pause_until") or brand.get("pause_until")) if effective_brand_status == "PAUSED" else None
            store.update(derive_outlet_runtime_state(store))
        return {**brand, "outlets": stores}


def request_status(brand_id: str, status: str, admin_id: str, pause_until=None) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """UPDATE vb_brands
                   SET requested_status=%s, requested_pause_until=%s,
                       pause_until=CASE WHEN %s='PAUSED' THEN pause_until ELSE NULL END,
                       requested_at=now(), requested_by=%s, updated_at=now()
                   WHERE id=%s AND is_active=true
                   RETURNING id, name, applied_status, requested_status,
                             requested_at, requested_pause_until""",
                (status, pause_until if status == "PAUSED" else None, status, admin_id, brand_id),
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
            outlets_for_brand = conn.execute(
                """SELECT bo.outlet_id, os.vercel_status, os.shopee_actual_status
                   FROM vb_brand_outlets bo
                   LEFT JOIN outlet_states os ON os.outlet_id = bo.outlet_id
                   WHERE bo.vb_brand_id = %s""",
                (brand_id,),
            ).fetchall()
            admin_action = "ADMIN_PAUSE_STORE" if status in ("PAUSED", "OFF") else "ADMIN_RESUME_STORE"
            target_state = "PAUSED" if status == "PAUSED" else ("CLOSED" if status == "OFF" else "OPEN")
            reason_text = "Outlet ditutup oleh Admin via Dashboard VB" if status in ("PAUSED", "OFF") else "Outlet dibuka oleh Admin via Dashboard VB"
            for out in outlets_for_brand:
                conn.execute(
                    """INSERT INTO automation_logs
                       (outlet_id, mode, vb_brand_id, suspension_status, subscription_status,
                        vercel_status_before, shopee_status_before, target_status, action,
                        success, error_message, reason)
                       VALUES (%s, 'VB', %s, 'ACTIVE', 'ACTIVE', %s, %s, %s, %s, true, NULL, %s)""",
                    (out["outlet_id"], brand_id, out["vercel_status"] or "OFF",
                     out["shopee_actual_status"] or "UNKNOWN", target_state, admin_action, reason_text),
                )
            return row


import uuid


def _build_single_brand_detail(conn, brand_row: dict[str, Any], store_controls: dict[str, dict[str, Any]]) -> dict[str, Any]:
    brand_id = brand_row["id"]
    stores = list(conn.execute(
        """SELECT o.store_id, o.long_name, p.name AS merchant_name,
                  os.shopee_actual_status, os.shopee_regular_hours, os.shopee_special_hours, os.timezone,
                  os.schedule_fetch_status,
                  os.schedule_fetch_attempted_at::text AS schedule_fetch_attempted_at,
                  os.schedule_fetch_succeeded_at::text AS schedule_fetch_succeeded_at,
                  COALESCE(os.schedule_fetch_error, '') AS schedule_fetch_error
           FROM vb_brand_outlets bo
           JOIN outlets o ON o.id=bo.outlet_id AND o.is_active=true
           JOIN portals p ON p.id=o.portal_id AND p.is_active=true
           LEFT JOIN outlet_states os ON os.outlet_id=o.id
           WHERE bo.vb_brand_id=%s
             AND o.store_id ~ '^[0-9]+$'
             AND p.name !~* '^(status|status import|import status)$'
           ORDER BY p.name, o.store_id""",
        (brand_id,),
    ).fetchall())

    opened_count = 0
    failure_count = 0
    closed_count = 0
    first_valid_schedule = None
    first_special_hours = None

    for store in stores:
        control = store_controls.get(str(store["store_id"]), {})
        effective_status = control.get("status", "ON")
        reg_hours = normalize_shopee_regular_hours(store.get("shopee_regular_hours"))
        store["shopee_regular_hours"] = reg_hours
        store["shopee_special_hours"] = store.get("shopee_special_hours") or []
        store["timezone"] = normalize_timezone(store.get("timezone"))
        store["shopee_status"] = store.get("shopee_actual_status") or "UNKNOWN"
        store["vercel_status"] = "ON" if effective_status == "ON" else "OFF"
        effective_brand_status = brand_row.get("requested_status") or brand_row.get("applied_status") or "ON"
        store["pause_until"] = (brand_row.get("requested_pause_until") or brand_row.get("pause_until")) if effective_brand_status == "PAUSED" else None
        runtime_state = derive_outlet_runtime_state(store)
        store.update(runtime_state)

        live = store.get("live_state") or "UNKNOWN"
        is_error = bool(store.get("schedule_fetch_error") or store.get("bot_phase") == "ACTION_FAILED")
        if is_error:
            failure_count += 1
        elif live == "OPEN":
            opened_count += 1
        elif live in ("CLOSED", "PAUSE"):
            closed_count += 1
        else:
            failure_count += 1

        if not first_valid_schedule and any(reg_hours.values()):
            first_valid_schedule = reg_hours
            first_special_hours = store.get("shopee_special_hours") or []

    history_logs = list(conn.execute(
        """SELECT al.id, to_char(al.checked_at AT TIME ZONE 'Asia/Jakarta', 'YYYY-MM-DD HH24:MI:SS') AS timestamp,
                  COALESCE(o.store_id, '') AS store_id,
                  COALESCE(o.long_name, p.name, b.name) AS store_name,
                  p.name AS portal_name,
                  al.action, al.target_status, al.success, COALESCE(al.reason, '') AS reason
           FROM automation_logs al
           JOIN vb_brands b ON b.id=al.vb_brand_id
           LEFT JOIN outlets o ON o.id=al.outlet_id
           LEFT JOIN portals p ON p.id=o.portal_id
           WHERE al.vb_brand_id=%s
           ORDER BY al.id DESC LIMIT 10""",
        (brand_id,),
    ).fetchall())

    slug = slugify(brand_row["name"])
    is_schedule_locked = len(stores) > 0 and all(
        s.get("bot_phase") == "WAITING_SCHEDULE" or s.get("within_operating_schedule") is False
        for s in stores
    )

    effective_status = brand_row.get("requested_status") or brand_row.get("applied_status") or "ON"
    owner_name = brand_row.get("owner_name") or "VB"
    owner_slug = brand_row.get("owner_slug") or slugify(owner_name)

    return {
        "id": brand_row["id"],
        "name": brand_row["name"],
        "slug": slug,
        "owner_name": owner_name,
        "owner_slug": owner_slug,
        "applied_status": brand_row["applied_status"],
        "requested_status": brand_row["requested_status"],
        "effective_status": effective_status,
        "pause_until": brand_row["pause_until"] if effective_status == "PAUSED" else None,
        "requested_pause_until": brand_row["requested_pause_until"] if effective_status == "PAUSED" else None,
        "is_schedule_locked": is_schedule_locked,
        "status_counts": {
            "opened": opened_count,
            "failure": failure_count,
            "close": closed_count,
            "total": len(stores),
        },
        "schedule": {
            "regular_hours": first_valid_schedule or {},
            "special_hours": first_special_hours or [],
        },
        "outlets": stores,
        "history_logs": history_logs,
    }


def get_brand_by_slug_or_id(slug_or_id: str) -> dict[str, Any] | None:
    """Fetch complete brand data for public brand dashboard by slug or ID."""
    cleaned_target = (slug_or_id or "").strip()
    if not cleaned_target:
        return None

    with get_db_connection() as conn:
        store_controls = _store_control_map(conn)
        target_norm = cleaned_target.casefold()

        all_active_brands = list(conn.execute(
            """SELECT id, name, applied_status, requested_status, requested_at,
                      pause_until, requested_pause_until, last_applied_at, last_patrolled_at,
                      COALESCE(owner_name, 'VB') AS owner_name,
                      COALESCE(owner_slug, '') AS owner_slug
               FROM vb_brands WHERE is_active=true
               ORDER BY name_normalized"""
        ).fetchall())

        for b in all_active_brands:
            if not b.get("owner_slug"):
                b["owner_slug"] = slugify(b.get("owner_name") or "")

        # 1. Check if slug matches an owner_slug directly
        owner_matched_brands = [b for b in all_active_brands if b["owner_slug"] == target_norm]

        if owner_matched_brands:
            detailed_brands = [_build_single_brand_detail(conn, b, store_controls) for b in owner_matched_brands]
            primary_brand = detailed_brands[0]
            owner_name = primary_brand.get("owner_name") or "VB"
            owner_slug = primary_brand.get("owner_slug") or slugify(owner_name)
            return {
                **primary_brand,
                "owner_name": owner_name,
                "owner_slug": owner_slug,
                "brands": detailed_brands,
                "brand_count": len(detailed_brands),
            }

        # 2. Check if slug matches a brand ID or brand slug
        parsed_uuid = None
        try:
            parsed_uuid = str(uuid.UUID(cleaned_target))
        except (ValueError, AttributeError):
            pass

        target_brand = None
        for b in all_active_brands:
            b_slug = slugify(b["name"])
            if (parsed_uuid and str(b["id"]) == parsed_uuid) or (cleaned_target.isdigit() and str(b["id"]) == cleaned_target) or b_slug == target_norm or b["name"].strip().casefold() == target_norm:
                target_brand = b
                break

        if not target_brand:
            return None

        # Find all sibling brands under the same owner
        target_owner_slug = target_brand["owner_slug"]
        sibling_brands = [b for b in all_active_brands if b["owner_slug"] == target_owner_slug]
        detailed_brands = [_build_single_brand_detail(conn, b, store_controls) for b in sibling_brands]
        
        # Ensure target brand is first in list
        detailed_brands.sort(key=lambda item: 0 if str(item["id"]) == str(target_brand["id"]) else 1)
        primary_brand = detailed_brands[0]
        owner_name = primary_brand.get("owner_name") or "VB"
        owner_slug = primary_brand.get("owner_slug") or slugify(owner_name)

        return {
            **primary_brand,
            "owner_name": owner_name,
            "owner_slug": owner_slug,
            "brands": detailed_brands,
            "brand_count": len(detailed_brands),
        }


def request_brand_status_public(slug_or_id: str, status: str, pause_until=None) -> dict[str, Any] | None:
    """Execute brand toggle directly from public brand dashboard."""
    brand = get_brand_by_slug_or_id(slug_or_id)
    if not brand:
        return None
    brand_id = brand["id"]
    with get_db_connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """UPDATE vb_brands
                   SET requested_status=%s, requested_pause_until=%s,
                       pause_until=CASE WHEN %s='PAUSED' THEN pause_until ELSE NULL END,
                       requested_at=now(), requested_by=NULL, updated_at=now()
                   WHERE id=%s AND is_active=true
                   RETURNING id, name, applied_status, requested_status,
                             requested_at, requested_pause_until""",
                (status, pause_until if status == "PAUSED" else None, status, brand_id),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """INSERT INTO admin_audit_logs
                   (admin_account_id, vb_brand_id, action, old_value, new_value, reason)
                   VALUES (NULL, %s, 'VB_CONTROL_STATUS_REQUESTED', %s, %s, %s)""",
                (brand_id,
                 Jsonb({"applied_status": row["applied_status"]}),
                 Jsonb({"requested_status": row["requested_status"]}),
                 "Perubahan status diminta oleh Brand melalui Dashboard Brand"),
            )
            outlets_for_brand = conn.execute(
                """SELECT bo.outlet_id, os.vercel_status, os.shopee_actual_status
                   FROM vb_brand_outlets bo
                   LEFT JOIN outlet_states os ON os.outlet_id = bo.outlet_id
                   WHERE bo.vb_brand_id = %s""",
                (brand_id,),
            ).fetchall()
            brand_action = "USER_PAUSE_STORE" if status in ("PAUSED", "OFF") else "USER_RESUME_STORE"
            target_state = "PAUSED" if status == "PAUSED" else ("CLOSED" if status == "OFF" else "OPEN")
            reason_text = "Outlet ditutup oleh Brand" if status in ("PAUSED", "OFF") else "Outlet dibuka oleh Brand"
            for out in outlets_for_brand:
                conn.execute(
                    """INSERT INTO automation_logs
                       (outlet_id, mode, vb_brand_id, suspension_status, subscription_status,
                        vercel_status_before, shopee_status_before, target_status, action,
                        success, error_message, reason)
                       VALUES (%s, 'VB', %s, 'ACTIVE', 'ACTIVE', %s, %s, %s, %s, true, NULL, %s)""",
                    (out["outlet_id"], brand_id, out["vercel_status"] or "OFF",
                     out["shopee_actual_status"] or "UNKNOWN", target_state, brand_action, reason_text),
                )
            return row


def _parse_matrix(content: str) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return []
    headers = [h.strip().casefold() for h in rows[0]]
    is_relational = any("outlet" in h or "brand" in h for h in headers) and any("store" in h for h in headers)

    if is_relational:
        col_owner = next((i for i, h in enumerate(headers) if "owner" in h or "pemilik" in h), -1)
        col_outlet = next((i for i, h in enumerate(headers) if "outlet" in h or "brand" in h), -1)
        col_portal = next((i for i, h in enumerate(headers) if "portal" in h or "merchant" in h), -1)
        col_store_id = next((i for i, h in enumerate(headers) if "store" in h), -1)
        col_status = next((i for i, h in enumerate(headers) if "status" in h), -1)

        brands_map: dict[str, dict[str, Any]] = {}
        for row_number, row in enumerate(rows[1:], start=2):
            if not row or not any(cell.strip() for cell in row):
                continue

            def get_val(idx: int) -> str:
                return row[idx].strip() if 0 <= idx < len(row) else ""

            brand_raw = get_val(col_outlet)
            portal_raw = get_val(col_portal)
            store_id_raw = get_val(col_store_id)
            owner_raw = get_val(col_owner)
            status_raw = get_val(col_status) if col_status >= 0 else "Aktif"

            # Strict Validation Gate:
            # 1. Brand must be non-empty
            # 2. Portal must be non-empty
            # 3. Store ID must be purely numeric digits
            if not brand_raw or not portal_raw or not store_id_raw or not store_id_raw.isdigit():
                continue

            normalized_portal = normalize_portal_name(portal_raw)
            normalized_b = normalize_brand(brand_raw)
            is_active = status_raw.casefold() == "aktif" if status_raw else True

            if normalized_b not in brands_map:
                brands_map[normalized_b] = {
                    "row_number": row_number,
                    "brand": brand_raw,
                    "owner": owner_raw,
                    "status": status_raw or "Aktif",
                    "is_active": is_active,
                    "stores": [],
                }

            brands_map[normalized_b]["stores"].append({
                "store_id": store_id_raw,
                "source_column": normalized_portal,
                "owner": owner_raw,
            })

        return [b for b in brands_map.values() if b["stores"]]

    # Fallback to legacy matrix format
    status_index = next(
        (index for index, header in enumerate(headers)
         if header in {"status", "status import", "import status"}),
        None,
    )
    matrix = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not row[0].strip():
            continue
        status = row[status_index].strip() if status_index is not None and status_index < len(row) else "Aktif"
        is_active = status.casefold() == "aktif"
        stores = []
        for col_index, value in enumerate(row[1:], start=1):
            if col_index == status_index:
                continue
            header_name = headers[col_index].strip() if col_index < len(headers) else ""
            if header_name in {"status", "status import", "import status", "nama outlet asli"}:
                continue
            clean_val = value.strip()
            clean_portal = normalize_portal_name(header_name)
            if clean_val and clean_val.isdigit() and clean_portal:
                stores.append({
                    "store_id": clean_val,
                    "source_column": clean_portal,
                })
        if stores:
            matrix.append({"row_number": row_number, "brand": row[0].strip(), "status": status, "is_active": is_active, "stores": stores})
    return matrix


def import_sheet(admin_id: str) -> dict[str, Any]:
    response = requests.get(VB_SHEET_URL, timeout=20)
    response.raise_for_status()
    matrix = _parse_matrix(response.content.decode("utf-8"))
    brands_created = 0
    outlets_linked = 0
    outlets_created = 0
    brands_deactivated = 0
    brands_activated = 0
    portal_mismatches: list[dict[str, Any]] = []
    missing_store_ids: list[dict[str, Any]] = []
    with get_db_connection() as conn:
        with conn.transaction():
            incoming_names = {normalize_brand(item["brand"]) for item in matrix}
            if incoming_names:
                stale_brands = conn.execute(
                    "SELECT id, is_active FROM vb_brands WHERE is_active=true AND name_normalized <> ALL(%s)",
                    (list(incoming_names),),
                ).fetchall()
                if stale_brands:
                    conn.execute(
                        "UPDATE vb_brands SET is_active=false, updated_at=now() WHERE is_active=true AND name_normalized <> ALL(%s)",
                        (list(incoming_names),),
                    )
                    brands_deactivated += len(stale_brands)
            owner = conn.execute("SELECT id FROM merchants WHERE name=%s", (VB_OWNER_NAME,)).fetchone()
            if not owner:
                owner = conn.execute("INSERT INTO merchants (name) VALUES (%s) RETURNING id", (VB_OWNER_NAME,)).fetchone()
            owner_id = owner["id"]
            for item in matrix:
                existing_brand = conn.execute(
                    "SELECT is_active FROM vb_brands WHERE name_normalized=%s",
                    (normalize_brand(item["brand"]),),
                ).fetchone()
                owner_name = item.get("owner") or "VB"
                owner_slug = slugify(owner_name)
                brand = conn.execute(
                    """INSERT INTO vb_brands (name, name_normalized, is_active, owner_name, owner_slug)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (name_normalized) DO UPDATE SET
                         name=EXCLUDED.name, is_active=EXCLUDED.is_active,
                         owner_name=EXCLUDED.owner_name, owner_slug=EXCLUDED.owner_slug,
                         updated_at=now()
                       RETURNING id, is_active, (xmax = 0) AS inserted""",
                    (item["brand"], normalize_brand(item["brand"]), item["is_active"], owner_name, owner_slug),
                ).fetchone()
                if brand["inserted"]:
                    brands_created += 1
                elif existing_brand and existing_brand["is_active"] != item["is_active"]:
                    if item["is_active"]:
                        brands_activated += 1
                    else:
                        brands_deactivated += 1
                if not item["is_active"]:
                    continue
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
                           ON CONFLICT (outlet_id)
                           DO UPDATE SET vb_brand_id=EXCLUDED.vb_brand_id, source_column=EXCLUDED.source_column""",
                        (brand["id"], outlet["id"], store["source_column"]),
                    )
                    outlets_linked += 1
            admin_row = None
            if admin_id and str(admin_id) != "00000000-0000-0000-0000-000000000000":
                admin_row = conn.execute("SELECT id FROM dashboard_accounts WHERE id=%s", (admin_id,)).fetchone()
            if not admin_row:
                admin_row = conn.execute("SELECT id FROM dashboard_accounts ORDER BY id LIMIT 1").fetchone()
            if admin_row:
                conn.execute(
                    """INSERT INTO admin_audit_logs (admin_account_id, action, new_value, reason)
                       VALUES (%s, 'VB_IMPORT', %s, %s)""",
                    (admin_row["id"], Jsonb({"brands_seen": len(matrix), "brands_created": brands_created, "brands_activated": brands_activated, "brands_deactivated": brands_deactivated, "outlets_created": outlets_created, "outlets_linked": outlets_linked}),
                     "Import matrix Virtual Brand dari Google Sheet"),
                )
    return {
        "brands_seen": len(matrix),
        "brands_active": sum(1 for item in matrix if item["is_active"]),
        "brands_created": brands_created,
        "brands_activated": brands_activated,
        "brands_deactivated": brands_deactivated,
        "outlets_created": outlets_created,
        "outlets_linked": outlets_linked,
        "missing_store_ids": missing_store_ids,
        "portal_mismatches": portal_mismatches,
    }
