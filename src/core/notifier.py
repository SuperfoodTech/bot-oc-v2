"""
src/core/notifier.py
====================
Modul Notifier Discord Webhook untuk mengirim notifikasi eror bot patroli.
Format: Bahasa Indonesia, to the point, hanya menggunakan emoji ❌ untuk penanda eror.
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


def _is_vb_environment(is_vb: bool = False) -> bool:
    return is_vb or bool(os.getenv("VB_SHOPEE_USERNAME"))


def _get_webhook_url(is_vb: bool = False) -> str:
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

    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        try:
            from pathlib import Path
            import dotenv
            base_dir = Path(__file__).resolve().parent
            for _ in range(5):
                env_candidate = base_dir / ".env"
                if env_candidate.exists():
                    vals = dotenv.dotenv_values(str(env_candidate))
                    url = vals.get("DISCORD_WEBHOOK_URL", "").strip()
                    if url:
                        break
                base_dir = base_dir.parent
        except Exception:
            pass
    return url



def _get_footer_text(is_vb: bool = False) -> str:
    if _is_vb_environment(is_vb):
        return "FoodMaster Virtual Brand Engine"
    return "FoodMaster Bot Patrol Engine"


def _is_duplicate(signature: str) -> bool:
    now = time.time()
    with _CACHE_LOCK:
        # Cleanup expired items
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
                    "User-Agent": "FoodMasterBot/1.0"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception as e:
            # Tidak melempar exception ke luar agar tidak merusak alur kerja utama bot
            print(f"[NOTIFIER ERROR] Gagal mengirim webhook Discord: {e}")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def send_discord_error(
    *args,
    message: str = None,
    title: str = "❌ Eror Bot Patroli",
    logger_name: str = None,
    extra_fields: dict = None,
    platform: str = None,
    merchant: str = None,
    outlet: str = None,
    error_type: str = None,
    is_vb: bool = False,
    phone: str = None,
    **kwargs
):
    """
    Event error handler:
    - Discord: Ditiadakan (No-Op), karena Discord eksklusif hanya untuk Rekap VB Group (send_discord_vb_group_summary).
    - WhatsApp Gateway: Diteruskan khusus Bot-OC via send_wa_webhook_async jika phone tersedia.
    """
    if not _is_vb_environment(is_vb):
        target_phone = phone or (extra_fields.get("phone") if isinstance(extra_fields, dict) else None)
        if not target_phone and args and len(args) > 4:
            target_phone = str(args[4])
        if target_phone:
            send_wa_webhook_async(
                event_type="BOT_ERROR",
                phone=target_phone,
                merchant=merchant or "Shopee Merchant",
                outlet=outlet or "Outlet",
                platform=platform or "Shopee",
                error_type=error_type or "ACTION_FAILED",
                detail=message or title,
                is_vb=False
            )
    return


def send_discord_success(
    merchant: str,
    outlet: str,
    action: str,
    platform: str = "Shopee",
    store_id: str = None,
    message: str = None,
    is_vb: bool = False,
    phone: str = None,
    **kwargs
):
    """
    Event success handler:
    - Discord: Ditiadakan (No-Op), karena Discord eksklusif hanya untuk Rekap VB Group.
    - WhatsApp Gateway: Diteruskan khusus Bot-OC via send_wa_webhook_async jika phone tersedia.
    """
    if not _is_vb_environment(is_vb) and phone:
        act = str(action).upper()
        event = "ACTION_OPEN" if act in ("OPEN", "BUKA", "ACTION_OPEN", "USER_RESUME_STORE") else "ACTION_CLOSE"
        send_wa_webhook_async(
            event_type=event,
            phone=phone,
            merchant=merchant,
            outlet=outlet,
            platform=platform,
            store_id=store_id,
            action=action,
            is_vb=False
        )
    return


def send_discord_skipped(
    merchant: str,
    outlet: str,
    action: str,
    live_status: str,
    expected_status: str,
    platform: str = "Shopee",
    store_id: str = None,
    message: str = None,
    is_vb: bool = False,
    phone: str = None,
    **kwargs
):
    """
    Event skipped handler:
    - Discord: Ditiadakan (No-Op), karena Discord eksklusif hanya untuk Rekap VB Group.
    - WhatsApp Gateway: Diteruskan khusus Bot-OC via send_wa_webhook_async jika phone tersedia.
    """
    if not _is_vb_environment(is_vb) and phone:
        send_wa_webhook_async(
            event_type="ACTION_SKIPPED",
            phone=phone,
            merchant=merchant,
            outlet=outlet,
            platform=platform,
            store_id=store_id,
            action=action,
            live_status=live_status,
            detail=f"Expected: {expected_status}, Live: {live_status}",
            is_vb=False
        )
    return



def send_wa_webhook_async(
    event_type: str,
    phone: str,
    merchant: str,
    outlet: str,
    platform: str = "Shopee",
    store_id: str = None,
    action: str = None,
    live_status: str = None,
    error_type: str = None,
    detail: str = None,
    timestamp: str = None,
    is_vb: bool = False
):
    """
    Mengirimkan webhook notifikasi asinkron ke microservice bot-wa Gateway (Node.js).
    Notifikasi WhatsApp hanya dikirim khusus untuk outlet Bot-OC (Virtual Brand di-bypass).
    """
    if _is_vb_environment(is_vb):
        return

    wa_gateway_url = os.getenv("WA_GATEWAY_URL", "").strip()
    wa_api_key = os.getenv("WA_GATEWAY_KEY", "").strip()

    if not wa_gateway_url or not phone:
        return

    now_str = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB")

    payload = {
        "event_type": event_type,
        "phone": phone,
        "platform": platform,
        "merchant_name": merchant,
        "outlet_name": outlet,
        "store_id": store_id,
        "action": action,
        "live_status": live_status,
        "error_type": error_type,
        "detail": detail,
        "timestamp": now_str
    }

    def _worker():
        try:
            target_url = f"{wa_gateway_url.rstrip('/')}/api/v1/webhook/bot-action"
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                target_url,
                data=data_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": wa_api_key,
                    "User-Agent": "FoodMasterBot/1.0"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as e:
            print(f"[WA WEBHOOK ERROR] Gagal mengirim webhook ke bot-wa: {e}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def send_discord_vb_group_summary(
    group_name: str,
    action: str,
    success_items: list,
    failed_items: list = None,
    is_guarding: bool = False,
    is_vb: bool = True
):
    """
    Mengirim notifikasi rekap aksi per-VB Group ke Discord Webhook khusus Virtual Brand.
    Mendukung mode Group Toggle (Kolektif) dan mode Auto-Guarding (Targeted Outlet).
    Mendukung status Full Success (🟢 BUKA / 🔴 TUTUP) & Partial Success (🟠 SEBAGIAN).
    """
    webhook_url = _get_webhook_url(is_vb=is_vb)
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
            link_md = f" • [Link](https://shopee.co.id/universal-link/now-food/shop/{safe_id})"
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

    sig_raw = f"{title}:{group_name}:{action_word}:{success_count}:{failed_count}"
    sig_hash = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()

    if _is_duplicate(sig_hash):
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "footer": {
            "text": _get_footer_text(is_vb=is_vb)
        }
    }

    _send_payload_async(webhook_url, {"embeds": [embed]})
