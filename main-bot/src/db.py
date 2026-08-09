"""Compatibility import for the unified monorepo state adapter.

The active implementation lives in ``src/backend/state.py`` and reads the
Google Sheet. This module exists only for legacy bot entry points while they
are being consolidated; it does not open or configure a database.
"""

import sys
from pathlib import Path
from datetime import datetime

UNIFIED_SRC = Path(__file__).resolve().parents[2] / "src"
if str(UNIFIED_SRC) not in sys.path:
    sys.path.insert(0, str(UNIFIED_SRC))

from backend.state import *  # noqa: F401,F403


def fetch_merchant_outlets_from_db():
    """Return bot targets from PostgreSQL; the spreadsheet is import-only."""
    from sheets import MerchantOutlet

    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT o.store_id,o.long_name,p.name AS merchant_name,m.name AS owner,
                      COALESCE(sa.username, %s) AS username,
                      COALESCE(sa.password_plain, %s) AS password,
                      COALESCE(sa.phone, '') AS phone,
                      COALESCE(os.vercel_status, 'OFF') AS control_status,
                      COALESCE(os.shopee_actual_status, 'UNKNOWN') AS actual_status,
                      COALESCE(os.suspension_status, 'ACTIVE') AS suspension_status,
                      COALESCE(os.suspension_reason, '') AS suspension_reason,
                      COALESCE(sp.name, 'Paket 3 Bulan') AS plan,
                      s.start_date::text AS start_date,s.end_date::text AS end_date,
                      o.special_hours
               FROM outlets o JOIN merchants m ON m.id=o.merchant_id
               JOIN portals p ON p.id=o.portal_id
               LEFT JOIN shopee_accounts sa ON sa.id=o.shopee_account_id
               LEFT JOIN outlet_states os ON os.outlet_id=o.id
               LEFT JOIN LATERAL (SELECT * FROM subscriptions sx WHERE sx.outlet_id=o.id ORDER BY sx.end_date DESC LIMIT 1) s ON true
               LEFT JOIN subscription_plans sp ON sp.id=s.plan_id
               WHERE o.is_active=true
               ORDER BY p.name,o.store_id""",
            (BOT_USERNAME, BOT_PASSWORD),
        ).fetchall()

    return [MerchantOutlet(
        kepemilikan="",
        paket=row["plan"],
        tanggal_mulai_layanan=row["start_date"] or "",
        tanggal_berakhir_layanan=row["end_date"] or "",
        hp=row["phone"], username=BOT_USERNAME, password=BOT_PASSWORD,
        nama_pemilik=row["owner"], nama_portal=row["merchant_name"], merchant_id="",
        store_id=row["store_id"], nama_panjang_outlet=row["long_name"],
        status_utama=row["control_status"], status_aktual=row["actual_status"],
        vercel_password="", special_hours=row["special_hours"] or "",
        status_langganan="Kedaluwarsa" if row["end_date"] and row["end_date"] < datetime.now().date().isoformat() else "Aktif",
        penangguhan="Ya" if row["suspension_status"] == "SUSPENDED" else "Tidak",
        alasan_penangguhan=row["suspension_reason"],
    ) for row in rows]
