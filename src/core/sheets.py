"""Parser for the current Google Sheet outlet import CSV."""

import csv
import io
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SHEETS_CSV_URL = os.getenv(
    "GOOGLE_SHEETS_CSV_URL",
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSTEPFClRQogVXYHNo3PRN4m91wHoKHSpS6Dg5Ofj08JFZdoCS9apvvh3C2OTVpqpebFk6xhaQs6ljY/"
    "pub?gid=0&single=true&output=csv",
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
    """A row from the current A-K import layout."""

    nama_pemilik: str = ""                 # A
    import_status: str = "Aktif"           # B: Aktif/Nonaktif import gate
    kepemilikan: str = ""                  # Legacy compatibility; not persisted or used for routing
    paket: str = ""                        # C
    tanggal_mulai_layanan: str = ""        # D
    tanggal_berakhir_layanan: str = ""     # E
    username: str = ""                     # F
    password: str = ""                     # G: Shopee account password
    nama_portal: str = ""                  # H
    store_id: str = ""                     # I
    nama_panjang_outlet: str = ""          # J
    vercel_password: str = ""              # K: dashboard password
    status_utama: str = "ON"          # Database default for new outlets only
    status_aktual: str = "UNKNOWN"
    merchant_id: str = ""
    nama_pendek_outlet: str = ""
    vercel_link: str = ""
    regular_hours: dict = field(default_factory=dict)
    special_hours: str = ""
    status_langganan: str = "Aktif"
    penangguhan: str = "Tidak"
    alasan_penangguhan: str = ""
    tgl_mulai_penangguhan: str = ""
    tgl_berakhir_penangguhan: str = ""
    # Stored local end time for a user-requested temporary pause.
    pause_until: str = ""
    hp: str = ""


def _subscription_status(end_date: str) -> str:
    if not end_date:
        return "Aktif"
    try:
        return "Aktif" if datetime.strptime(end_date, "%Y-%m-%d") >= datetime.now() else "Kedaluwarsa"
    except ValueError:
        return "Aktif"


def fetch_merchant_outlets(csv_url: str = GOOGLE_SHEETS_CSV_URL) -> List[MerchantOutlet]:
    """Download and parse the current A-L CSV layout."""
    response = requests.get(csv_url, timeout=15)
    response.raise_for_status()
    reader = csv.reader(io.StringIO(response.content.decode("utf-8-sig")))
    rows = list(reader)
    if not rows:
        return []

    outlets: List[MerchantOutlet] = []
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue

        def get_col(index: int) -> str:
            return row[index].strip() if index < len(row) else ""

        end_date = get_col(4)
        outlets.append(MerchantOutlet(
            nama_pemilik=get_col(0),
            import_status=get_col(1),
            paket=get_col(2),
            tanggal_mulai_layanan=get_col(3),
            tanggal_berakhir_layanan=end_date,
            username=get_col(5),
            password=get_col(6),
            nama_portal=get_col(7),
            store_id=get_col(8),
            nama_panjang_outlet=get_col(9),
            vercel_password=get_col(10),
            status_langganan=_subscription_status(end_date),
        ))
    return outlets
