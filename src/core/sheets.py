"""
core/sheets.py
==============
Module to fetch and parse merchant outlet data from the published Google Sheets CSV control source.
Uses dynamic header-name index mapping to ensure column accuracy regardless of padding/order.
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
    Uses dynamic column name resolution for accurate parsing.
    """
    resp = requests.get(csv_url, timeout=15)
    resp.raise_for_status()

    content = resp.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    
    rows = list(reader)
    if not rows:
        return []

    # Dynamic header column resolver
    header_lower = [h.strip().lower() for h in rows[0]]

    def find_col_idx(substring: str, fallback_idx: int) -> int:
        for idx, h in enumerate(header_lower):
            if substring.lower() in h:
                return idx
        return fallback_idx

    idx_utama       = find_col_idx("status utama", 14)
    idx_vercel_lnk  = find_col_idx("vercel link", 15)
    idx_vercel_pwd  = find_col_idx("vercel kata sandi", 16)
    idx_senin       = find_col_idx("senin", 17)
    idx_selasa      = find_col_idx("selasa", 18)
    idx_rabu        = find_col_idx("rabu", 19)
    idx_kamis       = find_col_idx("kamis", 20)
    idx_jumat       = find_col_idx("jumat", 21)
    idx_sabtu       = find_col_idx("sabtu", 22)
    idx_minggu      = find_col_idx("minggu", 23)
    idx_notes       = find_col_idx("notes", 24)
    idx_langganan   = find_col_idx("status langganan", 33)
    idx_penangguhan = find_col_idx("penangguhan", 34)
    idx_alasan      = find_col_idx("alasan", 35)
    idx_mulai_p     = find_col_idx("tanggal mulai penangguhan", 36)
    idx_akhir_p     = find_col_idx("tanggal berakhir penangguhan", 37)
    idx_aktual      = find_col_idx("status aktual", 38)

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

        tgl_berakhir = get_col(4)
        status_langganan_raw = get_col(idx_langganan)
        if not status_langganan_raw:
            if tgl_berakhir:
                try:
                    dt = datetime.strptime(tgl_berakhir, "%Y-%m-%d")
                    status_langganan_raw = "Aktif" if dt >= datetime.now() else "Kedaluwarsa"
                except Exception:
                    status_langganan_raw = "Aktif"
            else:
                status_langganan_raw = "Aktif"

        outlet = MerchantOutlet(
            aplikator=aplikator,
            kepemilikan=get_col(1),
            paket=get_col(2),
            tanggal_mulai_layanan=get_col(3),
            tanggal_berakhir_layanan=tgl_berakhir,
            hp=get_col(5),
            username=get_col(6),
            password=get_col(7),
            nama_pemilik=get_col(8),
            nama_portal=get_col(9),
            merchant_id=get_col(10),
            store_id=get_col(11),
            nama_panjang_outlet=get_col(12),
            nama_pendek_outlet=get_col(13),
            status_utama=get_col(idx_utama),
            status_aktual=get_col(idx_aktual),
            vercel_link=get_col(idx_vercel_lnk),
            vercel_password=get_col(idx_vercel_pwd),
            regular_hours={
                "Senin": get_col(idx_senin),
                "Selasa": get_col(idx_selasa),
                "Rabu": get_col(idx_rabu),
                "Kamis": get_col(idx_kamis),
                "Jumat": get_col(idx_jumat),
                "Sabtu": get_col(idx_sabtu),
                "Minggu": get_col(idx_minggu),
            },
            special_hours=get_col(idx_notes),
            status_langganan=status_langganan_raw,
            penangguhan=get_col(idx_penangguhan) or "Tidak",
            alasan_penangguhan=get_col(idx_alasan),
            tgl_mulai_penangguhan=get_col(idx_mulai_p),
            tgl_berakhir_penangguhan=get_col(idx_akhir_p),
        )
        outlets.append(outlet)

    return outlets
