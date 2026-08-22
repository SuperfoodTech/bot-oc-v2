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


def _get_webhook_url() -> str:
    return os.getenv("DISCORD_WEBHOOK_URL", "").strip()


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
    **kwargs
):
    """
    Mengirim notifikasi eror ke Discord Webhook secara asinkron dan to the point.
    Mendukung pemanggilan positional (platform, merchant, error_type, message, extra)
    maupun keyword arguments (message, title, logger_name, extra_fields, dll).
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return

    # Parse positional args if provided (legacy browser.py signature support)
    # Style 1: (platform, merchant, error_type, message, extra_info)
    # Style 2: (message, title, logger_name, extra_fields)
    if args:
        if len(args) >= 4 and args[0] in ("Shopee", "GrabFood", "Gofood") or (len(args) >= 3 and not message):
            # Positional style from browser.py: (platform, merchant, error_type, message, ...)
            if platform is None and len(args) > 0: platform = str(args[0])
            if merchant is None and len(args) > 1: merchant = str(args[1])
            if error_type is None and len(args) > 2: error_type = str(args[2])
            if message is None and len(args) > 3: message = str(args[3])
            if len(args) > 4:
                extra_fields = extra_fields or {}
                extra_fields["Detail"] = str(args[4])
        else:
            # Positional style: (message, title, logger_name, extra_fields)
            if message is None and len(args) > 0: message = str(args[0])
            if title == "❌ Eror Bot Patroli" and len(args) > 1: title = str(args[1])
            if logger_name is None and len(args) > 2: logger_name = str(args[2])
            if extra_fields is None and len(args) > 3 and isinstance(args[3], dict): extra_fields = args[3]

    if not message:
        message = "Terjadi eror pada sistem patroli."

    if error_type and title == "❌ Eror Bot Patroli":
        title = f"❌ Eror Bot Patroli: {error_type}"

    # Buat signature spesifik per merchant & outlet agar notifikasi toko berbeda tidak ter-suppress
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

    # Limit message length for Discord Embed Description (max 2000 chars)
    trimmed_msg = message[:1900] + ("..." if len(message) > 1900 else "")

    embed = {
        "title": title,
        "description": trimmed_msg,
        "color": 15158332,  # Merah #E74C3C
        "fields": fields,
        "footer": {
            "text": "FoodMaster Bot Patrol Engine"
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
    message: str = None
):
    """
    Mengirim notifikasi sukses saat outlet berhasil di-OPEN atau di-CLOSE / PAUSE.
    """
    webhook_url = _get_webhook_url()
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
            "text": "FoodMaster Bot Patrol Engine"
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
    message: str = None
):
    """
    Mengirim notifikasi informasi (di-SKIP) ketika status live Shopee pasca-aksi
    berbeda dari ekspektasi (misal karena ada Jadwal Khusus / Libur di Shopee).
    """
    webhook_url = _get_webhook_url()
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
            "text": "FoodMaster Bot Patrol Engine"
        }
    }

    payload = {
        "embeds": [embed]
    }

    _send_payload_async(webhook_url, payload)



