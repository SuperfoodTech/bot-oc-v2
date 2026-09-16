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
    return is_vb or bool(os.getenv("VB_SHOPEE_USERNAME")) or bool(os.getenv("DISCORD_WEBHOOK_VB_URL"))


def _get_webhook_url(is_vb: bool = False) -> str:
    if _is_vb_environment(is_vb):
        vb_url = os.getenv("DISCORD_WEBHOOK_VB_URL", "").strip()
        if vb_url:
            return vb_url
    return os.getenv("DISCORD_WEBHOOK_URL", "").strip()


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
    **kwargs
):
    """
    Mengirim notifikasi eror ke Discord Webhook secara asinkron dan to the point.
    Mendukung pemanggilan positional (platform, merchant, error_type, message, extra)
    maupun keyword arguments (message, title, logger_name, extra_fields, dll).
    """
    webhook_url = _get_webhook_url(is_vb=is_vb)
    if not webhook_url:
        return

    # Parse positional args if provided (legacy browser.py signature support)
    if args:
        if len(args) >= 4 and args[0] in ("Shopee", "GrabFood", "Gofood") or (len(args) >= 3 and not message):
            if platform is None and len(args) > 0: platform = str(args[0])
            if merchant is None and len(args) > 1: merchant = str(args[1])
            if error_type is None and len(args) > 2: error_type = str(args[2])
            if message is None and len(args) > 3: message = str(args[3])
            if len(args) > 4:
                extra_fields = extra_fields or {}
                extra_fields["Detail"] = str(args[4])
        else:
            if message is None and len(args) > 0: message = str(args[0])
            if title == "❌ Eror Bot Patroli" and len(args) > 1: title = str(args[1])
            if logger_name is None and len(args) > 2: logger_name = str(args[2])
            if extra_fields is None and len(args) > 3 and isinstance(args[3], dict): extra_fields = args[3]

    if not message:
        message = "Terjadi eror pada sistem patroli."

    if error_type and title == "❌ Eror Bot Patroli":
        title = f"❌ Eror Bot Patroli: {error_type}"

    sig_raw = f"{title}:{error_type}:{platform}:{merchant}:{outlet}:{logger_name}:{message}"
    sig_hash = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()

    if _is_duplicate(sig_hash):
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fields = []
    if platform:
        fields.append({"name": "Platform", "value": f"`{platform}`", "inline": True})
    if merchant:
        fields.append({"name": "Merchant Name", "value": f"`{merchant}`", "inline": True})
    if outlet:
        fields.append({"name": "Outlet Name", "value": f"`{outlet}`", "inline": True})
    if error_type:
        fields.append({"name": "Tipe Error", "value": f"`{error_type}`", "inline": True})
    if logger_name:
        explicit_mod = MODULE_NAME_MAP.get(logger_name, logger_name)
        fields.append({"name": "Modul", "value": f"`{explicit_mod}`", "inline": True})
    
    fields.append({"name": "Waktu", "value": now_str, "inline": True})

    if extra_fields:
        for k, v in extra_fields.items():
            fields.append({"name": str(k), "value": str(v), "inline": True})

    trimmed_msg = message[:1900] + ("..." if len(message) > 1900 else "")

    embed = {
        "title": title,
        "description": trimmed_msg,
        "color": 15158332,  # Merah #E74C3C
        "fields": fields,
        "footer": {
            "text": _get_footer_text(is_vb=is_vb)
        }
    }

    payload = {
        "embeds": [embed]
    }

    _send_payload_async(webhook_url, payload)


def send_discord_success(
    merchant: str,
    outlet: str,
    action: str,
    platform: str = "Shopee",
    store_id: str = None,
    message: str = None,
    is_vb: bool = False
):
    """
    Mengirim notifikasi sukses saat outlet berhasil di-OPEN atau di-CLOSE / PAUSE.
    """
    webhook_url = _get_webhook_url(is_vb=is_vb)
    if not webhook_url:
        return

    act = str(action).upper()
    is_open = act in ("OPEN", "BUKA", "ACTION_OPEN", "USER_RESUME_STORE")
    
    status_label = "BERHASIL DIBUKA (OPEN)" if is_open else "BERHASIL DITUTUP (CLOSE)"
    emoji = "🟢" if is_open else "🟡"
    color = 3066993 if is_open else 15844367  # Hijau #2ECC71 untuk OPEN, Kuning #F1C40F untuk CLOSE

    title = f"{emoji} Outlet {status_label}"
    
    if not message:
        message = f"Outlet **{outlet}** pada Merchant **{merchant}** berhasil di-{ 'OPEN' if is_open else 'CLOSE' }."

    sig_raw = f"{title}:{platform}:{merchant}:{outlet}:{act}"
    sig_hash = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()

    if _is_duplicate(sig_hash):
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fields = [
        {"name": "Platform", "value": f"`{platform}`", "inline": True},
        {"name": "Merchant Name", "value": f"`{merchant}`", "inline": True},
        {"name": "Outlet Name", "value": f"`{outlet}`", "inline": True},
    ]

    if store_id:
        fields.append({"name": "Store ID", "value": f"`{store_id}`", "inline": True})

    fields.append({"name": "Status Aksi", "value": f"`{'OPEN' if is_open else 'CLOSE'}`", "inline": True})
    fields.append({"name": "Waktu", "value": now_str, "inline": True})

    embed = {
        "title": title,
        "description": message,
        "color": color,
        "fields": fields,
        "footer": {
            "text": _get_footer_text(is_vb=is_vb)
        }
    }

    payload = {
        "embeds": [embed]
    }

    _send_payload_async(webhook_url, payload)


def send_discord_skipped(
    merchant: str,
    outlet: str,
    action: str,
    live_status: str,
    expected_status: str,
    platform: str = "Shopee",
    store_id: str = None,
    message: str = None,
    is_vb: bool = False
):
    """
    Mengirim notifikasi informasi (di-SKIP) ketika status live Shopee pasca-aksi
    berbeda dari ekspektasi (misal karena ada Jadwal Khusus / Libur di Shopee).
    """
    webhook_url = _get_webhook_url(is_vb=is_vb)
    if not webhook_url:
        return

    title = "⚠️ Status Outlet Berbeda (Di-SKIP)"
    color_orange = 15105570  # Orange #E67E22

    if not message:
        message = (
            f"Outlet **{outlet}** pada Merchant **{merchant}** di-SKIP dari paksa status.\n"
            f"Status Live Shopee pasca-eksekusi adalah **{live_status}**, sedangkan ekspektasi dari aksi **{action}** adalah **{expected_status}**.\n"
            f"*Kemungkinan toko memiliki Jadwal Khusus / Libur atau belum memiliki jadwal di Shopee.*"
        )

    sig_raw = f"{title}:{platform}:{merchant}:{outlet}:{action}:{live_status}:{expected_status}"
    sig_hash = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()

    if _is_duplicate(sig_hash):
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fields = [
        {"name": "Platform", "value": f"`{platform}`", "inline": True},
        {"name": "Merchant Name", "value": f"`{merchant}`", "inline": True},
        {"name": "Outlet Name", "value": f"`{outlet}`", "inline": True},
    ]

    if store_id:
        fields.append({"name": "Store ID", "value": f"`{store_id}`", "inline": True})

    fields.append({"name": "Status Live Shopee", "value": f"`{live_status}`", "inline": True})
    fields.append({"name": "Ekspektasi Aksi", "value": f"`{expected_status}`", "inline": True})
    fields.append({"name": "Status Bot", "value": "`DI-SKIP (Jadwal Khusus)`", "inline": True})
    fields.append({"name": "Waktu", "value": now_str, "inline": True})

    embed = {
        "title": title,
        "description": message,
        "color": color_orange,
        "fields": fields,
        "footer": {
            "text": _get_footer_text(is_vb=is_vb)
        }
    }

    payload = {
        "embeds": [embed]
    }

    _send_payload_async(webhook_url, payload)


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
    is_vb: bool = True
):
    """
    Mengirim notifikasi rekap aksi per-VB Group ke Discord Webhook khusus Virtual Brand.
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

    if failed_count == 0:
        # Sukses Total (All Succeeded)
        emoji = "🟢" if is_open else "🔴"
        title = f"{emoji} VB GROUP BERHASIL {action_word} BOT"
        color = 3066993 if is_open else 15158332
        hasil_str = f"{success_count} Berhasil"
    elif success_count == 0:
        # Gagal Total (All Failed)
        emoji = "🔴"
        title = f"🔴 VB GROUP GAGAL {action_word} BOT"
        color = 15158332  # Merah Alert #E74C3C
        hasil_str = f"{failed_count} Gagal"
    else:
        # Sebagian Berhasil (Partial Success)
        emoji = "🟠"
        title = f"🟠 VB GROUP SEBAGIAN BERHASIL {action_word} BOT"
        color = 15105570  # Orange #E67E22
        hasil_str = f"{success_count} Berhasil, {failed_count} Gagal"

    lines = [
        f"**VB Group:** {group_name}",
        f"**Hasil:** {hasil_str}",
        ""
    ]

    def _format_item(item):
        if isinstance(item, dict):
            name = item.get("name", "Listing")
            info = item.get("store_id") or item.get("link") or ""
        elif isinstance(item, (tuple, list)):
            name = str(item[0])
            info = str(item[1]) if len(item) > 1 else ""
        else:
            name = str(item)
            info = ""
        return f"{name} — {info}".strip(" —")

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
