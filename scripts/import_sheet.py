#!/usr/bin/env python3
"""One-time/master import of spreadsheet columns B-Y into PostgreSQL."""

from backend import db
from core.sheets import fetch_merchant_outlets


def run_import_sheet() -> int:
    db.init_db()
    rows = fetch_merchant_outlets()
    for row in rows:
        db.save_or_update_store(
            store_id=row.store_id,
            store_name=row.nama_panjang_outlet or row.nama_pendek_outlet,
            merchant_name=row.nama_portal,
            account_username=row.username,
            nama_pemilik=row.nama_pemilik,
            paket=row.paket,
            tanggal_mulai_layanan=row.tanggal_mulai_layanan,
            tanggal_berakhir_layanan=row.tanggal_berakhir_layanan,
            vercel_password=row.vercel_password,
            vercel_status=(row.status_utama or "OFF").upper(),
            shopee_status="UNKNOWN",
            subscription_status=row.status_langganan,
            regular_hours=row.regular_hours,
            special_hours=row.special_hours,
        )
    return len(rows)


def main():
    count = run_import_sheet()
    print(f"Imported {count} spreadsheet rows into PostgreSQL.")


if __name__ == "__main__":
    main()
