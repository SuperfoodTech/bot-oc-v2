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


def send_discord_error(*args, **kwargs):
    """
    No-Op Stub: Notifikasi eror individual ditiadakan untuk Virtual Brand di Discord.
    Notifikasi Discord Virtual Brand beroperasi secara eksklusif hanya untuk Rekap VB Group (Skenario 1.1 - 1.6).
    """
    return




def send_discord_success(*args, **kwargs):
    """
    No-Op Stub: Notifikasi sukses per-outlet individual ditiadakan untuk Virtual Brand.
    Notifikasi Virtual Brand dipusatkan secara eksklusif via Rekap Per-Group (send_discord_vb_group_summary).
    """
    return


def send_discord_skipped(*args, **kwargs):
    """
    No-Op Stub: Notifikasi di-SKIP per-outlet individual ditiadakan untuk Virtual Brand.
    Notifikasi Virtual Brand dipusatkan secara eksklusif via Rekap Per-Group (send_discord_vb_group_summary).
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
    Mengirim notifikasi rekap aksi per-VB Group ke Discord Webhook khusus Virtual Brand.
    Mendukung mode Group Toggle (Kolektif) dan mode Auto-Guarding (Targeted Outlet).
    Mendukung status Full Success (🟢 BUKA / 🔴 TUTUP) & Partial Success (🟠 SEBAGIAN).
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return

    act = str(action).upper()
    is_open = act in ("OPEN", "BUKA", "ACTION_OPEN", "USER_RESUME_STORE")
    action_word = "DIBUKA" if is_open else "DITUTUP"

    success_list = success_items or []
    failed_list = failed_items or []

    success_count = len(success_list)
    failed_count = len(failed_list)

    if success_count == 0 and failed_count == 0:
        return

    entity_label = "OUTLET (GUARDING)" if is_guarding else "GROUP"

    if failed_count == 0:
        # Sukses Total (All Succeeded)
        emoji = "🟢" if is_open else "🔴"
        title = f"{emoji} VB {entity_label} BERHASIL {action_word} BOT"
        color = 3066993 if is_open else 15158332
        hasil_str = f"{success_count} Outlet Berhasil {action_word.capitalize()}" if is_guarding else f"{success_count} Berhasil"
    elif success_count == 0:
        # Gagal Total (All Failed)
        emoji = "🔴"
        title = f"🔴 VB {entity_label} GAGAL {action_word} BOT"
        color = 15158332  # Merah Alert #E74C3C
        hasil_str = f"{failed_count} Outlet Gagal {action_word.capitalize()}" if is_guarding else f"{failed_count} Gagal"
    else:
        # Sebagian Berhasil (Partial Success)
        emoji = "🟠"
        title = f"🟠 VB {entity_label} SEBAGIAN BERHASIL {action_word} BOT"
        color = 15105570  # Orange #E67E22
        hasil_str = f"{success_count} Berhasil, {failed_count} Gagal"

    lines = [
        f"**VB Group:** {group_name}",
        f"**Hasil:** {hasil_str}",
        ""
    ]

    def _format_item(item):
        if isinstance(item, dict):
            name = item.get("name") or "Listing"
            info = item.get("store_id") or item.get("link") or ""
        elif isinstance(item, (tuple, list)):
            name = str(item[0]) if len(item) > 0 else "Listing"
            info = str(item[1]) if len(item) > 1 else ""
        else:
            name = str(item)
            info = ""
        formatted = f"{name} — {info}".strip(" —")
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
