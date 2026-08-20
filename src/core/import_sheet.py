"""Import active outlet rows from the published Google Sheet CSV."""

from backend import db
from core.sheets import fetch_merchant_outlets


def run_import_sheet() -> dict[str, int]:
    db.init_db()
    rows = fetch_merchant_outlets()

    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        if not row.store_id:
            continue
        if row.store_id in seen:
            duplicates.add(row.store_id)
        seen.add(row.store_id)
    if duplicates:
        ids = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplikat Store ID di Google Sheet: {ids}")

    imported = 0
    deactivated = 0
    skipped = 0
    for row in rows:
        if not row.store_id:
            skipped += 1
            continue
        if row.import_status.strip().casefold() != "aktif":
            if db.deactivate_store(row.store_id):
                deactivated += 1
            else:
                skipped += 1
            continue

        db.save_or_update_store(
            store_id=row.store_id,
            store_name=row.nama_panjang_outlet or row.store_id,
            merchant_name=row.nama_portal,
            account_username=row.username,
            account_password=row.password,
            nama_pemilik=row.nama_pemilik,
            ownership_type=row.kepemilikan,
            paket=row.paket,
            tanggal_mulai_layanan=row.tanggal_mulai_layanan,
            tanggal_berakhir_layanan=row.tanggal_berakhir_layanan,
            vercel_password=row.vercel_password,
            vercel_status="ON",
            shopee_status="UNKNOWN",
            subscription_status=row.status_langganan,
            is_active=True,
        )
        imported += 1

    return {"imported": imported, "deactivated": deactivated, "skipped": skipped}
