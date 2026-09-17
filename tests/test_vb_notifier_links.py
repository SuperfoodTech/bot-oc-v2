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


notifier_vb = _load_module("test_main_vb_notifier", "core/notifier.py")


class TestVbNotifierLinks(unittest.TestCase):
    def setUp(self):
        with notifier_vb._CACHE_LOCK:
            notifier_vb._NOTIFICATION_CACHE.clear()

    def test_item_formatting_with_store_id(self):
        # 1. Test success and failed items with store_ids
        success_items = [
            {"name": "Katsunami Rawamangun", "store_id": "1002345"},
            ("Katsunami Matraman", "1002346"),
        ]
        failed_items = [
            {"name": "Katsunami Tebet", "store_id": "1002347"},
        ]

        with patch.object(notifier_vb, "_get_webhook_url", return_value="https://discord.com/api/webhooks/mock"), \
             patch.object(notifier_vb, "_send_payload_async") as mock_send:
            notifier_vb.send_discord_vb_group_summary(
                group_name="Katsunami Group",
                action="ACTION_OPEN",
                success_items=success_items,
                failed_items=failed_items,
                is_guarding=False,
            )

            mock_send.assert_called_once()
            payload = mock_send.call_args[0][1]
            embed = payload["embeds"][0]
            desc = embed["description"]

            expected_link_1 = "✅ Katsunami Rawamangun — 1002345 • [Link](https://shopee.co.id/universal-link/now-food/shop/1002345)"
            expected_link_2 = "✅ Katsunami Matraman — 1002346 • [Link](https://shopee.co.id/universal-link/now-food/shop/1002346)"
            expected_link_3 = "❌ Katsunami Tebet — 1002347 • [Link](https://shopee.co.id/universal-link/now-food/shop/1002347)"

            self.assertIn(expected_link_1, desc)
            self.assertIn(expected_link_2, desc)
            self.assertIn(expected_link_3, desc)

    def test_item_formatting_fallback_without_store_id(self):
        # 2. Test plain item without store_id (graceful fallback)
        success_items = ["Outlet Tanpa ID"]
        with patch.object(notifier_vb, "_get_webhook_url", return_value="https://discord.com/api/webhooks/mock"), \
             patch.object(notifier_vb, "_send_payload_async") as mock_send:
            notifier_vb.send_discord_vb_group_summary(
                group_name="Simple Group",
                action="ACTION_CLOSE",
                success_items=success_items,
                is_guarding=True,
            )

            mock_send.assert_called_once()
            payload = mock_send.call_args[0][1]
            desc = payload["embeds"][0]["description"]

            self.assertIn("✅ Outlet Tanpa ID", desc)
            self.assertNotIn("[Link]()", desc)

    def test_guarding_mode_notification(self):
        # 3. Test Auto-Guarding mode
        success_items = [{"name": "Ayam Geprek Solo", "store_id": "999888"}]
        with patch.object(notifier_vb, "_get_webhook_url", return_value="https://discord.com/api/webhooks/mock"), \
             patch.object(notifier_vb, "_send_payload_async") as mock_send:
            notifier_vb.send_discord_vb_group_summary(
                group_name="Ayam Geprek",
                action="ACTION_CLOSE",
                success_items=success_items,
                is_guarding=True,
            )

            mock_send.assert_called_once()
            payload = mock_send.call_args[0][1]
            embed = payload["embeds"][0]
            self.assertIn("VB OUTLET (GUARDING) BERHASIL DITUTUP BOT", embed["title"])
            self.assertIn("✅ Ayam Geprek Solo — 999888 • [Link](https://shopee.co.id/universal-link/now-food/shop/999888)", embed["description"])


if __name__ == "__main__":
    unittest.main()
