"""
main-vb/src/core/notifier.py
============================
Modul Notifier Discord Webhook khusus Virtual Brand Engine (bot-vb).
Seluruh notifikasi Virtual Brand dikirimkan khusus ke Discord Webhook (DISCORD_WEBHOOK_VB_URL).
Pengiriman notifikasi WhatsApp (bot-wa) di-bypass secara penuh untuk Virtual Brand.
"""

import os
import json
import time
import hashlib
import threading
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# Cache deduplikasi notifikasi: {hash_signature: timestamp}
_NOTIFICATION_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 300  # 5 menit deduplikasi


# Mapping nama modul internal/technical ke nama yang lebih eksplisit & mudah dipahami
MODULE_NAME_MAP = {
    "browser": "Automasi Browser Shopee (Login & Switch)",
    "shopee_pro": "Engine Patroli Shopee",
    "backend_worker": "Worker Antrean Task Patroli",
    "client": "Shopee Seller API Client",
    "shopee.store_status": "Patroli Jam Operasional Toko",
    "shopee": "Modul Integrasi Shopee",
    "main": "Backend REST API Server",
    "uvicorn.error": "Web Server Uvicorn",
    "Shopee Browser Automation": "Automasi Browser Shopee (Login & Switch)",
    "Worker Task Patroli Engine": "Worker Antrean Task Patroli",
    "Shopee Seller API Client": "Shopee Seller API Client",
    "Patroli Jam Operasional Toko": "Patroli Jam Operasional Toko",
}


def _get_webhook_url() -> str:
    """
    Mengambil URL Webhook khusus Virtual Brand (DISCORD_WEBHOOK_VB_URL),
    dengan fallback ke DISCORD_WEBHOOK_URL jika belum dikonfigurasi.
    Mendukung dynamic reload dari .env dan .env.vb tanpa restart process.
    """
    vb_url = os.getenv("DISCORD_WEBHOOK_VB_URL", "").strip()
    if not vb_url:
        try:
            from pathlib import Path
            import dotenv
            base_dir = Path(__file__).resolve().parent
            for _ in range(5):
                env_candidate = base_dir / ".env"
                env_vb_candidate = base_dir / ".env.vb"
                if env_candidate.exists() or env_vb_candidate.exists():
                    if env_vb_candidate.exists():
                        vals = dotenv.dotenv_values(str(env_vb_candidate))
                        vb_url = vals.get("DISCORD_WEBHOOK_VB_URL", "").strip()
                    if not vb_url and env_candidate.exists():
                        vals = dotenv.dotenv_values(str(env_candidate))
                        vb_url = vals.get("DISCORD_WEBHOOK_VB_URL", "").strip() or vals.get("DISCORD_WEBHOOK_URL", "").strip()
                    if vb_url:
                        break
                base_dir = base_dir.parent
        except Exception:
            pass

    if vb_url:
        return vb_url
    return os.getenv("DISCORD_WEBHOOK_URL", "").strip()



def _get_footer_text() -> str:
    """
    Footer identitas khusus untuk seluruh notifikasi Virtual Brand.
    """
    return "FoodMaster Virtual Brand"


def _is_duplicate(signature: str) -> bool:
    now = time.time()
    with _CACHE_LOCK:
        expired = [k for k, v in _NOTIFICATION_CACHE.items() if now - v > _CACHE_TTL_SECONDS]
        for k in expired:
            del _NOTIFICATION_CACHE[k]

        if signature in _NOTIFICATION_CACHE:
            return True

        _NOTIFICATION_CACHE[signature] = now
        return False


def _send_payload_async(webhook_url: str, payload: dict):
    """
    Fungsi internal untuk mengirim payload HTTP POST ke Discord Webhook secara asinkron.
    """
    def worker():
        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=data_bytes,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "FoodMasterBot-VB/1.0"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception as e:
            print(f"[VB NOTIFIER ERROR] Gagal mengirim webhook Discord: {e}")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def send_discord_error(
    *args,
    message: str = None,
    title: str = "⚠️ Alert Force-Close Bot (Merchant Churn)",
    platform: str = "Shopee",
    merchant: str = None,
    outlet: str = None,
    error_type: str = None,
    store_id: str = None,
    **kwargs
):
    """
    Mengirimkan alert eror ke Discord jika bot gagal mengakses merchant (misal akses dicabut / unreachable).
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return

    # Extract args if called positionally: (platform, username, error_type, message, phone)
    if args:
        if len(args) > 0 and not platform:
            platform = str(args[0])
        if len(args) > 1 and not merchant:
            merchant = str(args[1])
        if len(args) > 2 and not error_type:
            error_type = str(args[2])
        if len(args) > 3 and not message:
            message = str(args[3])

    err_msg = message or "Terjadi kesalahan operasional pada bot terminator."
    target_portal = merchant or outlet or "N/A"
    store_str = f" | Store ID: {store_id}" if store_id else ""

    sig_raw = f"CLOSE_ERR:{target_portal}:{error_type}:{err_msg}"
    sig_hash = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()
    if _is_duplicate(sig_hash):
        return

    now_wib = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M:%S WIB")

    embed = {
        "title": f"🚨 [CLOSE-BOT] Error: {error_type or 'UNREACHABLE'}",
        "description": (
            f"Bot force-close gagal mengakses outlet/portal churn.\n\n"
            f"**Portal / Merchant**: {target_portal}{store_str}\n"
            f"**Platform**: {platform}\n"
            f"**Keterangan**: {err_msg}\n"
            f"**Waktu**: {now_wib}"
        ),
        "color": 0xDC2626,  # Red
        "footer": {
            "text": "FoodMaster Force-Close Terminator"
        }
    }

    _send_payload_async(webhook_url, {"embeds": [embed]})


def send_discord_success(*args, **kwargs):
    """
    No-Op: Notifikasi sukses ditiadakan untuk force-close bot.
    """
    return


def send_discord_skipped(*args, **kwargs):
    """
    No-Op: Notifikasi skipped ditiadakan untuk force-close bot.
    """
    return



def send_discord_vb_group_summary(
    group_name: str,
    action: str,
    success_items: list,
    failed_items: list = None,
    is_guarding: bool = False,
    **kwargs
):
    """
    Mengirim notifikasi rekap aksi per-VB Group ke Discord Webhook hanya jika ada error / kegagalan.
    Jika semua aksi berhasil, notifikasi di-silent.
    """
    failed_list = failed_items or []
    failed_count = len(failed_list)

    # Silent on 100% success for churn force-close bot
    if failed_count == 0:
        return

    webhook_url = _get_webhook_url()
    if not webhook_url:
        return

    act = str(action).upper()
    is_open = act in ("OPEN", "BUKA", "ACTION_OPEN", "USER_RESUME_STORE")
    action_word = "DIBUKA" if is_open else "DITUTUP"

    success_list = success_items or []
    success_count = len(success_list)

    entity_label = "OUTLET CHURN" if is_guarding else "PORTAL CHURN"
    if success_count == 0:
        # Gagal Total (All Failed)
        emoji = "🔴"
        title = f"🔴 VB {entity_label} GAGAL {action_word} BOT"
        color = 15158332  # Merah Alert #E74C3C
    else:
        # Sebagian Berhasil (Partial Success)
        emoji = "🟠"
        title = f"🟠 VB {entity_label} SEBAGIAN BERHASIL {action_word} BOT"
        color = 15105570  # Orange #E67E22

    lines = [
        f"**VB Group:** {group_name}",
        ""
    ]

    def _format_item(item):
        if isinstance(item, dict):
            name = item.get("name") or "Listing"
            store_id = str(item.get("store_id") or "").strip()
            info = store_id or str(item.get("link") or "").strip()
        elif isinstance(item, (tuple, list)):
            name = str(item[0]) if len(item) > 0 else "Listing"
            store_id = str(item[1]).strip() if len(item) > 1 else ""
            info = store_id
        else:
            name = str(item)
            store_id = ""
            info = ""
        formatted = f"{name} — {info}".strip(" —") if (name or info) else "Listing"
        if store_id:
            safe_id = urllib.parse.quote(store_id)
            link_md = f" • [Link](https://shopee.co.id/now-food/shop/{safe_id})"
            return f"{formatted}{link_md}"
        return formatted if formatted else "Listing"

    if success_count > 0:
        lines.append(f"**Berhasil {action_word} ({success_count}):**")
        for item in success_list:
            lines.append(f"✅ {_format_item(item)}")
        lines.append("")

    if failed_count > 0:
        lines.append(f"**Gagal {action_word} ({failed_count}):**")
        for item in failed_list:
            lines.append(f"❌ {_format_item(item)}")
        lines.append("")

    description = "\n".join(lines).strip()
    if len(description) > 3900:
        description = description[:3900] + "\n..."

    def _extract_id(item):
        if isinstance(item, dict):
            return str(item.get("store_id") or item.get("name") or "item")
        elif isinstance(item, (tuple, list)):
            return str(item[1] if len(item) > 1 else (item[0] if len(item) > 0 else "item"))
        return str(item)

    succ_ids = ",".join(sorted(_extract_id(item) for item in success_list))
    fail_ids = ",".join(sorted(_extract_id(item) for item in failed_list))

    sig_raw = f"{title}:{group_name}:{action_word}:{succ_ids}:{fail_ids}"
    sig_hash = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()


    if _is_duplicate(sig_hash):
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "footer": {
            "text": _get_footer_text()
        }
    }

    _send_payload_async(webhook_url, {"embeds": [embed]})


def send_wa_webhook_async(*args, **kwargs):
    """
    Stub No-Op khusus Virtual Brand: Notifikasi Virtual Brand (bot-vb) 100% dikirim ke Discord,
    dan TIDAK AKAN PERNAH memicu pengiriman notifikasi WhatsApp.
    """
    return
