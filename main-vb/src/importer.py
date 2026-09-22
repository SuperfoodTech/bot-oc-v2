"""Idempotent importer for the VB matrix spreadsheet."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

import requests

import db

DEFAULT_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSsAq8JmDfGI8KY7aSCRpzC2EaQARkK1OvhWrll7g3qlxFMIcwtDpAF-Wxf4aQnGET4eCmncjdEgre5/"
    "pub?gid=935753758&single=true&output=csv"
)

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


GENERIC_VB_OWNER_NAMES = {
    "",
    "-",
    "vb",
    "owner vb",
    "owner-vb",
    "virtual brand",
    "virtual-brand",
}


def normalize_owner_name(raw_owner: str | None) -> str:
    return " ".join((raw_owner or "").strip().split())


def is_generic_owner_name(raw_owner: str | None) -> bool:
    return normalize_owner_name(raw_owner).casefold() in GENERIC_VB_OWNER_NAMES


def slugify_owner_name(raw_owner: str | None) -> str:
    owner_name = normalize_owner_name(raw_owner)
    if not owner_name:
        return "vb"
    slug = re.sub(r"[^\w\s-]", "", owner_name).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug if slug != "brand" else "vb"


def resolve_brand_owner_name(item: dict[str, Any], existing_owner_name: str | None = None) -> str:
    owner_candidates = [item.get("owner")]
    owner_candidates.extend(store.get("owner") for store in (item.get("stores") or []))
    parsed_owner_name = next((owner for owner in (normalize_owner_name(value) for value in owner_candidates) if owner), "")
    persisted_owner_name = normalize_owner_name(existing_owner_name)

    if parsed_owner_name and not is_generic_owner_name(parsed_owner_name):
        return parsed_owner_name
    if persisted_owner_name and not is_generic_owner_name(persisted_owner_name):
        return persisted_owner_name
    return parsed_owner_name or persisted_owner_name or "VB"


def parse_matrix(content: str) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return []
    headers = [h.strip().casefold() for h in rows[0]]
    is_relational = any("outlet" in h or "brand" in h for h in headers) and any("store" in h for h in headers)

    if is_relational:
        col_owner = next((i for i, h in enumerate(headers) if any(token in h for token in ("owner", "pemilik", "pic"))), -1)
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
            owner_raw = normalize_owner_name(get_val(col_owner))
            status_raw = get_val(col_status) if col_status >= 0 else "Aktif"

            # Strict Validation Gate:
            # 1. Brand must be non-empty
            # 2. Portal must be non-empty
            # 3. Store ID must be purely numeric digits
            if not brand_raw or not portal_raw or not store_id_raw or not store_id_raw.isdigit():
                continue

            normalized_portal = normalize_portal_name(portal_raw)
            normalized_b = db.normalize_brand(brand_raw)
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
            elif not brands_map[normalized_b]["owner"] and owner_raw:
                brands_map[normalized_b]["owner"] = owner_raw

            brands_map[normalized_b]["stores"].append({
                "store_id": store_id_raw,
                "source_column": normalized_portal,
                "owner": owner_raw,
            })

        return [b for b in brands_map.values() if b["stores"]]

    # Fallback to legacy wide matrix format
    status_index = next(
        (index for index, header in enumerate(headers)
         if header in {"status", "status import", "import status"}),
        None,
    )
    output = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not row[0].strip():
            continue
        brand = row[0].strip()
        status = row[status_index].strip() if status_index is not None and status_index < len(row) else "Aktif"
        is_active = status.casefold() == "aktif"
        stores = []
        for index, store_id in enumerate(row[1:], start=1):
            if index == status_index:
                continue
            header_name = headers[index].strip() if index < len(headers) else ""
            if header_name in {"status", "status import", "import status", "nama outlet asli"}:
                continue
            clean_id = store_id.strip()
            clean_portal = normalize_portal_name(header_name)
            if clean_id and clean_id.isdigit() and clean_portal:
                stores.append({"store_id": clean_id, "source_column": clean_portal})
        if stores:
            output.append({"row_number": row_number, "brand": brand, "status": status, "is_active": is_active, "stores": stores})
    return output


def import_csv(content: str) -> dict[str, Any]:
    matrix = parse_matrix(content)
    created_brands = 0
    linked = 0
    missing_store_ids = []
    with db.connection() as conn:
        with conn.transaction():
            incoming_names = {db.normalize_brand(item["brand"]) for item in matrix}
            if incoming_names:
                conn.execute(
                    "UPDATE vb_brands SET is_active=false, updated_at=now() WHERE is_active=true AND name_normalized <> ALL(%s)",
                    (list(incoming_names),),
                )
            for item in matrix:
                normalized = db.normalize_brand(item["brand"])
                existing_brand = conn.execute(
                    "SELECT owner_name FROM vb_brands WHERE name_normalized=%s",
                    (normalized,),
                ).fetchone()
                owner_name = resolve_brand_owner_name(item, existing_brand["owner_name"] if existing_brand else None)
                owner_slug = slugify_owner_name(owner_name)
                brand = conn.execute(
                    """INSERT INTO vb_brands (name, name_normalized, is_active, owner_name, owner_slug)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (name_normalized) DO UPDATE SET
                         name=EXCLUDED.name,
                         is_active=EXCLUDED.is_active,
                         owner_name=EXCLUDED.owner_name,
                         owner_slug=EXCLUDED.owner_slug,
                         updated_at=now()
                       RETURNING id, applied_status, is_active, (xmax = 0) AS inserted""",
                    (item["brand"], normalized, item["is_active"], owner_name, owner_slug),
                ).fetchone()
                if brand["inserted"]:
                    created_brands += 1
                if not item["is_active"]:
                    continue
                for store in item["stores"]:
                    outlet = conn.execute("SELECT id FROM outlets WHERE store_id=%s AND is_active=true", (store["store_id"],)).fetchone()
                    if not outlet:
                        missing_store_ids.append({"brand": item["brand"], **store})
                        continue
                    conn.execute(
                        """INSERT INTO vb_brand_outlets (vb_brand_id, outlet_id, source_column)
                           VALUES (%s, %s, %s)
                           ON CONFLICT (outlet_id) DO UPDATE SET vb_brand_id=EXCLUDED.vb_brand_id, source_column=EXCLUDED.source_column""",
                        (brand["id"], outlet["id"], store["source_column"]),
                    )
                    linked += 1
    return {"brands_seen": len(matrix), "brands_defaulted_on": created_brands, "outlets_linked": linked, "missing_store_ids": missing_store_ids}


def import_url(url: str = DEFAULT_URL) -> dict[str, Any]:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return import_csv(response.content.decode("utf-8"))
