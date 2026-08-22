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
    "pub?gid=2099001096&single=true&output=csv"
)


def parse_matrix(content: str) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return []
    headers = rows[0]
    output = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not row[0].strip():
            continue
        brand = row[0].strip()
        stores = []
        for index, store_id in enumerate(row[1:], start=1):
            if store_id.strip():
                stores.append({"store_id": store_id.strip(), "source_column": headers[index].strip() if index < len(headers) else ""})
        output.append({"row_number": row_number, "brand": brand, "stores": stores})
    return output


def import_csv(content: str) -> dict[str, Any]:
    matrix = parse_matrix(content)
    created_brands = 0
    linked = 0
    missing_store_ids = []
    with db.connection() as conn:
        with conn.transaction():
            for item in matrix:
                normalized = db.normalize_brand(item["brand"])
                brand = conn.execute(
                    """INSERT INTO vb_brands (name, name_normalized)
                       VALUES (%s, %s)
                       ON CONFLICT (name_normalized) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                       RETURNING id, applied_status, (xmax = 0) AS inserted""", (item["brand"], normalized)
                ).fetchone()
                if brand["inserted"]:
                    created_brands += 1
                for store in item["stores"]:
                    outlet = conn.execute("SELECT id FROM outlets WHERE store_id=%s AND is_active=true", (store["store_id"],)).fetchone()
                    if not outlet:
                        missing_store_ids.append({"brand": item["brand"], **store})
                        continue
                    conn.execute(
                        """INSERT INTO vb_brand_outlets (vb_brand_id, outlet_id, source_column)
                           VALUES (%s, %s, %s)
                           ON CONFLICT (vb_brand_id, outlet_id) DO UPDATE SET source_column=EXCLUDED.source_column""",
                        (brand["id"], outlet["id"], store["source_column"]),
                    )
                    linked += 1
    return {"brands_seen": len(matrix), "brands_defaulted_on": created_brands, "outlets_linked": linked, "missing_store_ids": missing_store_ids}


def import_url(url: str = DEFAULT_URL) -> dict[str, Any]:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return import_csv(response.content.decode("utf-8"))
