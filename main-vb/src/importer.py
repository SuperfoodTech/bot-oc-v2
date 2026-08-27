"""Idempotent importer for the VB matrix spreadsheet."""

from __future__ import annotations

import csv
import io
from typing import Any

import requests

import db

DEFAULT_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSTEPFClRQogVXYHNo3PRN4m91wHoKHSpS6Dg5Ofj08JFZdoCS9apvvh3C2OTVpqpebFk6xhaQs6ljY/"
    "pub?gid=401458905&single=true&output=csv"
)


def parse_matrix(content: str) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return []
    headers = rows[0]
    status_index = next(
        (index for index, header in enumerate(headers)
         if header.strip().casefold() in {"status", "status import", "import status"}),
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
            if header_name.casefold() in {"status", "status import", "import status", "nama outlet asli"}:
                continue
            clean_id = store_id.strip()
            if clean_id and clean_id.isdigit():
                stores.append({"store_id": clean_id, "source_column": header_name})
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
                brand = conn.execute(
                    """INSERT INTO vb_brands (name, name_normalized, is_active)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (name_normalized) DO UPDATE SET
                         name=EXCLUDED.name, is_active=EXCLUDED.is_active, updated_at=now()
                       RETURNING id, applied_status, is_active, (xmax = 0) AS inserted""", (item["brand"], normalized, item["is_active"])
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
