import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core import import_sheet, sheets


def test_run_import_sheet_deactivates_stores_removed_from_sheet(monkeypatch: pytest.MonkeyPatch):
    mock_rows = [
        sheets.MerchantOutlet(
            nama_pemilik="Owner A",
            import_status="Aktif",
            paket="3 Bulan",
            tanggal_mulai_layanan="2026-09-01",
            tanggal_berakhir_layanan="2026-12-01",
            hp="08123456789",
            username="auto7313",
            password="pwd",
            nama_portal="Portal A",
            store_id="111111",
            nama_panjang_outlet="Outlet 1",
            vercel_password="123",
            status_langganan="Aktif",
        ),
        sheets.MerchantOutlet(
            nama_pemilik="Owner B",
            import_status="Nonaktif",
            paket="3 Bulan",
            tanggal_mulai_layanan="2026-09-01",
            tanggal_berakhir_layanan="2026-12-01",
            hp="08123456788",
            username="auto7313",
            password="pwd",
            nama_portal="Portal B",
            store_id="222222",
            nama_panjang_outlet="Outlet 2",
            vercel_password="123",
            status_langganan="Aktif",
        ),
    ]

    monkeypatch.setattr(import_sheet, "fetch_merchant_outlets", lambda: mock_rows)
    monkeypatch.setattr(import_sheet.db, "init_db", lambda: None)
    monkeypatch.setattr(import_sheet.db, "save_or_update_store", MagicMock())
    monkeypatch.setattr(import_sheet.db, "deactivate_store", MagicMock(return_value=True))
    
    mock_deactivate_missing = MagicMock(return_value=["333333", "444444"])
    monkeypatch.setattr(import_sheet.db, "deactivate_missing_agency_stores", mock_deactivate_missing)

    summary = import_sheet.run_import_sheet()

    assert summary["imported"] == 1
    assert summary["deactivated"] == 1
    assert summary["removed_from_sheet"] == 2
    assert summary["skipped"] == 0

    # Verify deactivate_missing_agency_stores was called with active store_ids in sheet
    mock_deactivate_missing.assert_called_once_with({"111111", "222222"})
