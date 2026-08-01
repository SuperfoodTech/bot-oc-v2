"""
core/sheets.py
==============
Module to fetch and parse merchant outlet data from the published Google Sheets CSV control source.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import requests

GOOGLE_SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSTEPFClRQogVXYHNo3PRN4m91wHoKHSpS6Dg5Ofj08JFZdoCS9apvvh3C2OTVpqpebFk6xhaQs6ljY/"
    "pub?gid=0&single=true&output=csv"
)

WEEKDAY_MAP = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}

@dataclass
class MerchantOutlet:
    aplikator: str
    kepemilikan: str
    paket: str
    tanggal_mulai_layanan: str
    tanggal_berakhir_layanan: str
    hp: str
    username: str
    password: str
    nama_pemilik: str
    nama_portal: str
    merchant_id: str
    store_id: str
    nama_panjang_outlet: str
    nama_pendek_outlet: str
    status_utama: str          # On / Off (Vercel Toggle - Source of Truth)
    status_aktual: str         # On / Busy / Close (Aktual Shopee)
    vercel_link: str
    vercel_password: str
    regular_hours: dict = field(default_factory=dict)  # {"Senin": "08:00-22:00", ...}
    special_hours: str = ""
    status_langganan: str = "Aktif"                    # Aktif / Kedaluwarsa
    penangguhan: str = "Tidak"                         # Ya / Tidak
    alasan_penangguhan: str = ""
    tgl_mulai_penangguhan: str = ""
    tgl_berakhir_penangguhan: str = ""

def fetch_merchant_outlets(csv_url: str = GOOGLE_SHEETS_CSV_URL) -> List[MerchantOutlet]:
    """
    Downloads the published CSV from Google Sheets and parses rows into MerchantOutlet objects.
    """
    resp = requests.get(csv_url, timeout=15)
    resp.raise_for_status()

    content = resp.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    
    rows = list(reader)
    if not rows:
        return []

    # Find header row or use index-based parsing
    header = rows[0]
    outlets = []

    for row in rows[1:]:
        if not row or not any(row):
            continue
        
        # Safe getter by index with fallback
        def get_col(idx: int) -> str:
            return row[idx].strip() if idx < len(row) else ""

        aplikator = get_col(0)
        if not aplikator or "shopee" not in aplikator.lower():
            # Skip non-Shopee or empty rows
            continue

        outlet = MerchantOutlet(
            aplikator=aplikator,
            kepemilikan=get_col(1),
            paket=get_col(2),
            tanggal_mulai_layanan=get_col(3),
            tanggal_berakhir_layanan=get_col(4),
            hp=get_col(5),
            username=get_col(6),
            password=get_col(7),
            nama_pemilik=get_col(8),
            nama_portal=get_col(9),
            merchant_id=get_col(10),
            store_id=get_col(11),
            nama_panjang_outlet=get_col(12),
            nama_pendek_outlet=get_col(13),
            status_utama=get_col(14),
            status_aktual=get_col(15),
            vercel_link=get_col(16),
            vercel_password=get_col(17),
            regular_hours={
                "Senin": get_col(18),
                "Selasa": get_col(19),
                "Rabu": get_col(20),
                "Kamis": get_col(21),
                "Jumat": get_col(22),
                "Sabtu": get_col(23),
                "Minggu": get_col(24),
            },
            special_hours=get_col(25),
            # Trailing columns (search by name or last columns)
            status_langganan=get_col(len(row) - 5) if len(row) >= 30 else "Aktif",
            penangguhan=get_col(len(row) - 4) if len(row) >= 30 else "Tidak",
            alasan_penangguhan=get_col(len(row) - 3) if len(row) >= 30 else "",
            tgl_mulai_penangguhan=get_col(len(row) - 2) if len(row) >= 30 else "",
            tgl_berakhir_penangguhan=get_col(len(row) - 1) if len(row) >= 30 else "",
        )
        outlets.append(outlet)

    return outlets
