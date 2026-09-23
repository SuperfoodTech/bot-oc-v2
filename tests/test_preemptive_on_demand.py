"""Test Preemptive Cooperative On-Demand Execution Engine."""

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "shopee"))
sys.path.insert(0, str(PROJECT_ROOT / "main-vb" / "src"))

from core.sheets import MerchantOutlet
import db as vb_db
import worker as vb_worker


def test_has_pending_brand_actions_with_mock_db():
    with patch("db.connection") as mock_conn:
        mock_cursor = MagicMock()
        mock_conn.return_value.__enter__.return_value = mock_cursor
        
        # When no pending brand requests exist
        mock_cursor.execute.return_value.fetchone.return_value = None
        assert vb_db.has_pending_brand_actions() is False

        # When pending brand requests exist
        mock_cursor.execute.return_value.fetchone.return_value = (1,)
        assert vb_db.has_pending_brand_actions() is True


def test_worker_preemption_yields_when_pending_action_detected():
    dummy_outlets = [
        MerchantOutlet(
            nama_pemilik="Test Brand",
            kepemilikan="VB",
            paket="",
            tanggal_mulai_layanan="",
            tanggal_berakhir_layanan="",
            username="auto7313",
            password="pwd",
            hp="0812345678",
            nama_portal="WonderFood",
            merchant_id="123",
            store_id=f"1000{i}",
            nama_panjang_outlet=f"Store {i}",
            nama_pendek_outlet=f"Store {i}",
            status_utama="ON",
            status_aktual="OPEN",
            regular_hours={"Senin": "08:00-20:00"},
            shopee_regular_hours={"Senin": "08:00-20:00"},
            shopee_special_hours=[],
            timezone="Asia/Jakarta",
            status_langganan="Aktif",
            penangguhan="Tidak",
            alasan_penangguhan="",
            pause_until="",
            schedule_fetch_status="READY",
            schedule_fetch_attempted_at="",
            schedule_fetch_succeeded_at="",
            schedule_fetch_error="",
        )
        for i in range(10)
    ]

    with patch.object(vb_db, "fetch_merchant_outlets_from_db", return_value=dummy_outlets), \
         patch.object(vb_db, "has_pending_brand_actions", side_effect=[False, True, True]), \
         patch.object(vb_worker.browser, "get_session", return_value={"driver": MagicMock(), "shopee_tob_token": "tok"}), \
         patch.object(vb_worker.store_status, "ensure_business_hours_page", return_value=True):

        result = vb_worker.sync_all_stores(
            execute_actions=False,
            target_store_ids=None,
        )

        assert result["yielded_for_preemption"] is True
