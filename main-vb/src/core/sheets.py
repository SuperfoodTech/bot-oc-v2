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
    shopee_regular_hours: dict = field(default_factory=dict)
    shopee_special_hours: list = field(default_factory=list)
    schedule_fetch_status: str = "NOT_FETCHED_YET"
    schedule_fetch_attempted_at: str = ""
    schedule_fetch_succeeded_at: str = ""
    schedule_fetch_error: str = ""
    hp: str = ""
    timezone: str = "Asia/Jakarta"


def _subscription_status(end_date: str) -> str:
    if not end_date:
        return "Aktif"
    try:
        return "Aktif" if datetime.strptime(end_date, "%Y-%m-%d") >= datetime.now() else "Kedaluwarsa"
    except ValueError:
        return "Aktif"


def fetch_merchant_outlets(csv_url: str = GOOGLE_SHEETS_CSV_URL) -> List[MerchantOutlet]:
    """Download and parse the Google Sheet CSV layout with header detection."""
    response = requests.get(csv_url, timeout=15)
    response.raise_for_status()
    reader = csv.reader(io.StringIO(response.content.decode("utf-8-sig")))
    rows = list(reader)
    if not rows:
        return []

    header = [cell.strip().casefold() for cell in rows[0]]

    def find_col(patterns: List[str], exclude: list = None, default: int = -1) -> int:
        for i, col in enumerate(header):
            if exclude and any(ex in col for ex in exclude):
                continue
            if any(pat in col for pat in patterns):
                return i
        return default

    col_nama_pemilik = find_col(["nama pemilik", "pemilik"], exclude=["wa", "hp"], default=0)
    col_hp = find_col(["wa", "whatsapp", "no hp", "hp"], default=-1)
    col_import_status = find_col(["status"], exclude=["langganan", "subscription"], default=1)
    col_paket = find_col(["paket", "package"], default=2)
    col_tanggal_mulai = find_col(["mulai", "start"], default=3)
    col_tanggal_berakhir = find_col(["berakhir", "expired", "end"], default=4)
    col_username = find_col(["username", "user"], exclude=["vercel", "dashboard"], default=5)
    col_password = find_col(["akses kata sandi", "kata sandi", "password", "pass"], exclude=["vercel", "dashboard"], default=6)
    col_nama_portal = find_col(["nama portal", "portal", "merchant"], default=7)
    col_store_id = find_col(["store id", "store_id", "store"], default=8)
    col_nama_panjang = find_col(["nama panjang", "panjang", "outlet"], exclude=["portal"], default=9)
    col_vercel_password = find_col(["vercel", "dashboard"], default=10)

    outlets: List[MerchantOutlet] = []
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue

        def get_val(idx: int) -> str:
            return row[idx].strip() if 0 <= idx < len(row) else ""

        end_date = get_val(col_tanggal_berakhir)
        outlets.append(MerchantOutlet(
            nama_pemilik=get_val(col_nama_pemilik),
            import_status=get_val(col_import_status),
            paket=get_val(col_paket),
            tanggal_mulai_layanan=get_val(col_tanggal_mulai),
            tanggal_berakhir_layanan=end_date,
            hp=get_val(col_hp),
            username=get_val(col_username),
            password=get_val(col_password),
            nama_portal=get_val(col_nama_portal),
            store_id=get_val(col_store_id),
            nama_panjang_outlet=get_val(col_nama_panjang),
            vercel_password=get_val(col_vercel_password),
            status_langganan=_subscription_status(end_date),
        ))
    return outlets
