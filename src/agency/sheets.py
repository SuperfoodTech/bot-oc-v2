"""
src/agency/sheets.py
====================
Parses Agency Google Sheet CSV data for ShopeeFood churn outlets.
"""

import csv
import io
import logging
import urllib.request
from typing import List, Dict, Tuple
from agency.config import AGENCY_SHEET_CSV_URL

log = logging.getLogger(__name__)


def fetch_agency_csv_data() -> List[Dict[str, str]]:
    """
    Fetches and parses raw rows from the Agency Google Sheet CSV URL.
    Returns a list of dicts mapped by column header names.
    """
    req = urllib.request.Request(
        AGENCY_SHEET_CSV_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8")

    reader = list(csv.reader(io.StringIO(content)))
    if not reader:
        return []

    headers = [h.strip() for h in reader[0]]
    results = []

    for row_idx, row in enumerate(reader[1:], start=2):
        if not row or all(cell.strip() == "" for cell in row):
            continue
        row_dict = {}
        for col_idx, header in enumerate(headers):
            val = row[col_idx].strip() if col_idx < len(row) else ""
            row_dict[header] = val
        results.append(row_dict)

    return results


def get_agency_shopeefood_outlets() -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Parses agency CSV data and filters ShopeeFood outlets.
    Returns a tuple: (churn_outlets, live_outlets)
    """
    all_rows = fetch_agency_csv_data()
    churn_list = []
    live_list = []

    for row in all_rows:
        aplikasi = row.get("Aplikasi", "").strip()
        if aplikasi.lower() != "shopeefood":
            continue

        outlet = row.get("Outlet", "").strip()
        brand = row.get("Brand", "").strip()
        merchant_name = row.get("Merchant Name", "").strip()
        store_id = row.get("Store ID", "").strip()
        status = row.get("Status", "").strip()
        nama_resto = row.get("Nama Resto Final", "").strip() or row.get("Nama Tarikan", "").strip()

        item = {
            "outlet": outlet,
            "brand": brand,
            "merchant_name": merchant_name,
            "store_id": store_id,
            "status": status,
            "nama_resto": nama_resto
        }

        if not store_id:
            continue

        if status.lower() == "churn":
            churn_list.append(item)
        elif status.lower() == "live":
            live_list.append(item)

    log.info("Agency CSV parsed: %d ShopeeFood Churn outlets, %d Live outlets", len(churn_list), len(live_list))
    return churn_list, live_list
