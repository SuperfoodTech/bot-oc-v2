"""
core/sheets.py
==============
Module to fetch and parse merchant outlet data from the published Google Sheets CSV control source.
Strictly parses Columns A through Y (indices 0 to 24).
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
    kepemilikan: str                # Col B (1); all rows are ShopeeFood
    paket: str                      # Col C (2)
    tanggal_mulai_layanan: str      # Col D (3)
    tanggal_berakhir_layanan: str  # Col E (4)
    hp: str                         # Col F (5)
    username: str                   # Col G (6)
    password: str                   # Col H (7)
    nama_pemilik: str               # Col I (8)
    nama_portal: str                # Col J (9)
    merchant_id: str                # Col K (10)
    store_id: str                   # Col L (11)
    nama_panjang_outlet: str        # Col M (12)
    status_utama: str               # Col O (14) - On / Off (Vercel Toggle - Source of Truth)
    status_aktual: str = "On"       # Live Shopee Status (On/Pause/Close)
    vercel_link: str = ""           # Col P (15)
    vercel_password: str = ""       # Col Q (16)
    regular_hours: dict = field(default_factory=dict)  # Cols R-X (17-23) {"Senin": "08:00-22:00", ...}
    special_hours: str = ""         # Col Y (24) Notes / Jam Spesial
    status_langganan: str = "Aktif" # Calculated from Col E (Tanggal Berakhir Layanan)
    penangguhan: str = "Tidak"      # Default: Tidak (Normal active subscription)
    alasan_penangguhan: str = ""
    tgl_mulai_penangguhan: str = ""
    tgl_berakhir_penangguhan: str = ""

def fetch_merchant_outlets(csv_url: str = GOOGLE_SHEETS_CSV_URL) -> List[MerchantOutlet]:
    """
    Downloads the published CSV from Google Sheets and parses rows strictly using Columns A through Y (0 to 24).
    Calculates status_langganan automatically from Column E (Tanggal Berakhir Layanan).
    """
    resp = requests.get(csv_url, timeout=15)
    resp.raise_for_status()

    content = resp.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    
    rows = list(reader)
    if not rows:
        return []

    outlets = []
    now = datetime.now()

    for row in rows[1:]:
        if not row or not any(row):
            continue
        
        # Safe getter by index (0 to 24)
        def get_col(idx: int) -> str:
            return row[idx].strip() if idx < len(row) else ""

        if not get_col(11):
            # Store ID is required for the Shopee-only service.
            continue

        # Column E (4): Tanggal Berakhir Layanan
        tgl_berakhir = get_col(4)
        
        # Calculate status_langganan automatically: "Aktif" if tgl_berakhir >= now else "Kedaluwarsa"
        if tgl_berakhir:
            try:
                dt = datetime.strptime(tgl_berakhir, "%Y-%m-%d")
                status_langganan_calc = "Aktif" if dt >= now else "Kedaluwarsa"
            except Exception:
                status_langganan_calc = "Aktif"
        else:
            status_langganan_calc = "Aktif"

        outlet = MerchantOutlet(
            kepemilikan=get_col(1),                     # Col B (1)
            paket=get_col(2),                           # Col C (2)
            tanggal_mulai_layanan=get_col(3),           # Col D (3)
            tanggal_berakhir_layanan=tgl_berakhir,      # Col E (4)
            hp=get_col(5),                              # Col F (5)
            username=get_col(6),                        # Col G (6)
            password=get_col(7),                        # Col H (7)
            nama_pemilik=get_col(8),                    # Col I (8)
            nama_portal=get_col(9),                     # Col J (9)
            merchant_id=get_col(10),                    # Col K (10)
            store_id=get_col(11),                       # Col L (11)
            nama_panjang_outlet=get_col(12),            # Col M (12)
            status_utama=get_col(14),                   # Col O (14) Status Utama (On/Off)
            status_aktual="On",                         # Live Shopee status
            vercel_link=get_col(15),                    # Col P (15)
            vercel_password=get_col(16),                # Col Q (16)
            regular_hours={                             # Cols R-X (17-23)
                "Senin": get_col(17),
                "Selasa": get_col(18),
                "Rabu": get_col(19),
                "Kamis": get_col(20),
                "Jumat": get_col(21),
                "Sabtu": get_col(22),
                "Minggu": get_col(23),
            },
            special_hours=get_col(24),                  # Col Y (24) Notes / Special Hours
            status_langganan=status_langganan_calc,     # Derived from Col E
            penangguhan="Tidak",                        # Default: Tidak
            alasan_penangguhan="",
            tgl_mulai_penangguhan="",
            tgl_berakhir_penangguhan="",
        )
        outlets.append(outlet)

    return outlets
