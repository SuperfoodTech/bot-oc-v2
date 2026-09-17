import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_VB_SRC = PROJECT_ROOT / "main-vb" / "src"
if str(MAIN_VB_SRC) not in sys.path:
    sys.path.insert(0, str(MAIN_VB_SRC))


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, MAIN_VB_SRC / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


db = _load_module("test_main_vb_db_flush", "db.py")


class TestVbNotificationFlush(unittest.TestCase):
    def setUp(self):
        with db._PENDING_LOCK:
            db._PENDING_BRAND_ACTIONS.clear()
            db._BRAND_TOGGLED_IDS.clear()

    def tearDown(self):
        with db._PENDING_LOCK:
            db._PENDING_BRAND_ACTIONS.clear()
            db._BRAND_TOGGLED_IDS.clear()

    def test_record_log_system_does_not_flush_notifications(self):
        with patch.object(db, "flush_pending_brand_notifications") as mock_flush:
            db.record_log(
                store_id="SYSTEM",
                store_name="BOT_DAEMON",
                action="SYNC_CYCLE",
                target_state="SYNCED",
                reason="Cycle done",
            )
            mock_flush.assert_not_called()

    @patch("core.notifier.send_discord_vb_group_summary")
    def test_flush_pending_brand_notifications_guarding_mode_only_shows_executed_outlets(self, mock_send_discord):
        # 1. Guarding mode: Only 1 outlet out of 5 was executed (auto-recovery)
        db._record_pending_brand_action(
            brand_id="brand-1",
            store_id="101",
            store_name="Katsunami - SuperFood",
            action="ACTION_OPEN",
            target_state="OPEN",
            success=True,
            error_message=None,
        )

        mock_conn = MagicMock()
        mock_brand = {"id": "brand-1", "name": "Katsunami", "applied_status": "ON"}

        def mock_execute(query, params=None):
            m = MagicMock()
            if "FROM vb_brands" in query:
                m.fetchone.return_value = mock_brand
            return m

        mock_conn.execute.side_effect = mock_execute

        with patch.object(db, "connection") as mock_conn_fn:
            mock_conn_fn.return_value.__enter__.return_value = mock_conn
            db.flush_pending_brand_notifications()

        mock_send_discord.assert_called_once()
        call_kwargs = mock_send_discord.call_args.kwargs
        self.assertEqual(call_kwargs["group_name"], "Katsunami")
        self.assertEqual(call_kwargs["action"], "ACTION_OPEN")
        self.assertTrue(call_kwargs["is_guarding"])
        self.assertEqual(len(call_kwargs["success_items"]), 1)
        self.assertEqual(call_kwargs["success_items"][0]["name"], "Katsunami - SuperFood")
        self.assertEqual(call_kwargs["success_items"][0]["store_id"], "101")
        self.assertEqual(len(call_kwargs["failed_items"]), 0)

    @patch("core.notifier.send_discord_vb_group_summary")
    def test_flush_pending_brand_notifications_brand_toggle_shows_collective_group(self, mock_send_discord):
        # 1. Brand toggle mode: Brand status was toggled
        with db._PENDING_LOCK:
            db._BRAND_TOGGLED_IDS.add("brand-1")

        db._record_pending_brand_action(
            brand_id="brand-1",
            store_id="101",
            store_name="Store Portal A",
            action="ACTION_CLOSE",
            target_state="CLOSED",
            success=True,
            error_message=None,
        )
        db._record_pending_brand_action(
            brand_id="brand-1",
            store_id="102",
            store_name="Store Portal B",
            action="ACTION_CLOSE",
            target_state="CLOSED",
            success=True,
            error_message=None,
        )

        mock_conn = MagicMock()
        mock_brand = {"id": "brand-1", "name": "Ayam Geprek Brand", "applied_status": "PAUSED"}
        mock_outlets = [
            {"store_id": "101", "name": "Store Portal A", "shopee_actual_status": "PAUSE", "vercel_status": "OFF"},
            {"store_id": "102", "name": "Store Portal B", "shopee_actual_status": "PAUSE", "vercel_status": "OFF"},
            {"store_id": "103", "name": "Store Portal C", "shopee_actual_status": "PAUSE", "vercel_status": "OFF"},
        ]

        def mock_execute(query, params=None):
            m = MagicMock()
            if "FROM vb_brands" in query:
                m.fetchone.return_value = mock_brand
            elif "FROM vb_brand_outlets" in query:
                m.fetchall.return_value = mock_outlets
            else:
                m.fetchall.return_value = []
                m.fetchone.return_value = None
            return m

        mock_conn.execute.side_effect = mock_execute

        with patch.object(db, "connection") as mock_conn_fn:
            mock_conn_fn.return_value.__enter__.return_value = mock_conn
            db.flush_pending_brand_notifications()

        mock_send_discord.assert_called_once()
        call_kwargs = mock_send_discord.call_args.kwargs
        self.assertEqual(call_kwargs["group_name"], "Ayam Geprek Brand")
        self.assertEqual(call_kwargs["action"], "ACTION_CLOSE")
        self.assertFalse(call_kwargs["is_guarding"])
        self.assertEqual(len(call_kwargs["success_items"]), 3)
        self.assertEqual(len(call_kwargs["failed_items"]), 0)


if __name__ == "__main__":
    unittest.main()
