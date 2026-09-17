# Spesifikasi Kontrak Backend API Webhook (`bot-wa`)

Dokumen ini berisi spesifikasi API Webhook, HTTP Headers, JSON Payload Schema, dan contoh integrasi client untuk komunikasi antara backend **bot-oc / bot-vb** (Python) dan **bot-wa Gateway Service** (Node.js).

---

## 1. Authentication & Headers

Setiap request dari backend ke `bot-wa` WAIB menyertakan header autentikasi berikut:

| Header Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| `Content-Type` | String | Must be `application/json` | Ya |
| `X-API-Key` | String | Secret token autentikasi API Gateway | Ya |

---

## 2. API Endpoints

### A. Webhook Action Notification
Menyampaikan notifikasi hasil aksi bot patroli (Buka/Tutup/Skip/Error) ke merchant/mitra.

- **URL Path**: `/api/v1/webhook/bot-action`
- **Method**: `POST`
- **Authentication**: Header `X-API-Key`

#### Payload Request Schema (JSON)

```json
{
  "phone": "6281234567890",
  "event_type": "ACTION_OPEN",
  "platform": "Shopee",
  "merchant_name": "Kopi Mantap",
  "outlet_name": "Kopi Mantap - Cabang Sudirman",
  "store_id": "22403325",
  "action": "OPEN",
  "live_status": "OPEN",
  "error_type": null,
  "detail": "Outlet berhasil dibuka sesuai jadwal operasional hari ini",
  "timestamp": "2026-09-16 11:00:00 WIB"
}
```

#### Field Description

| Field Name | Type | Options / Format | Required | Description |
| :--- | :--- | :--- | :--- | :--- |
| `phone` | String | Misal: `"6281234567890"` | Ya | Nomor WhatsApp tujuan merchant (format internasional tanpa `+`) |
| `event_type` | String | `ACTION_OPEN`, `ACTION_CLOSE`, `ACTION_SKIPPED`, `BOT_ERROR` | Ya | Jenis event notifikasi |
| `platform` | String | `"Shopee"`, `"GrabFood"`, `"GoFood"` | Ya | Platform toko |
| `merchant_name` | String | Misal: `"Kopi Mantap"` | Ya | Nama Merchant / Brand |
| `outlet_name` | String | Misal: `"Cabang Sudirman"` | Ya | Nama Outlet |
| `store_id` | String | Misal: `"22403325"` | Tidak | Store ID Shopee / Platform |
| `action` | String | `"OPEN"`, `"CLOSE"`, `"PAUSE"` | Tidak | Aksi yang dieksekusi bot |
| `live_status` | String | `"OPEN"`, `"CLOSED"`, `"PAUSE"` | Tidak | Status terkini di Shopee |
| `error_type` | String | Misal: `"StoreIdentityMismatch"` | Tidak | Tipe error jika `event_type = BOT_ERROR` |
| `detail` | String | Text penjelasan singkat | Tidak | Catatan tambahan / subteks status |
| `timestamp` | String | Format `"YYYY-MM-DD HH:mm:ss WIB"` | Tidak | Waktu kejadian |

---

### B. Direct Message API
Mengirimkan pesan teks kustom langsung ke nomor WhatsApp tertentu.

- **URL Path**: `/api/v1/send-message`
- **Method**: `POST`
- **Authentication**: Header `X-API-Key`

#### Request Payload:
```json
{
  "phone": "6281234567890",
  "message": "Halo, ini pesan langsung dari sistem FoodMaster."
}
```

---

### C. Connection Status Check API
Memeriksa status koneksi WhatsApp Gateway (QR, Connected, Disconnected).

- **URL Path**: `/api/v1/status`
- **Method**: `GET`
- **Authentication**: Header `X-API-Key`

#### Response Success (200 OK):
```json
{
  "success": true,
  "wa_status": "CONNECTED",
  "qr_code_raw": null,
  "queue_length": 0
}
```

---

## 3. Response Codes & Error Handling

| HTTP Code | Meaning | Description |
| :--- | :--- | :--- |
| `200 OK` | Success | Payload berhasil diterima dan dijadwalkan ke antrean pesan. |
| `400 Bad Request` | Invalid Request | Payload tidak lengkap (misal: `phone` atau `merchant_name` kosong). |
| `401 Unauthorized` | Invalid API Key | Header `X-API-Key` salah atau tidak disertakan. |
| `500 Internal Error` | Server Error | Terjadi masalah internal pada WhatsApp Gateway. |

---

## 4. Contoh Integrasi Client Python (`bot-oc` / `bot-vb`)

Berikut adalah snippet fungsi Python helper yang digunakan pada `src/core/notifier.py`:

```python
import os
import json
import threading
import urllib.request

def send_wa_webhook_async(event_type: str, phone: str, merchant: str, outlet: str, **kwargs):
    wa_gateway_url = os.getenv("WA_GATEWAY_URL", "").strip()
    wa_api_key = os.getenv("WA_GATEWAY_KEY", "").strip()

    if not wa_gateway_url or not phone:
        return

    payload = {
        "event_type": event_type,
        "phone": phone,
        "merchant_name": merchant,
        "outlet_name": outlet,
        "platform": kwargs.get("platform", "Shopee"),
        "store_id": kwargs.get("store_id"),
        "action": kwargs.get("action"),
        "live_status": kwargs.get("live_status"),
        "error_type": kwargs.get("error_type"),
        "detail": kwargs.get("detail"),
        "timestamp": kwargs.get("timestamp")
    }

    def _worker():
        try:
            req = urllib.request.Request(
                f"{wa_gateway_url.rstrip('/')}/api/v1/webhook/bot-action",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": wa_api_key
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as e:
            print(f"[WA WEBHOOK ERROR] Gagal mengirim webhook ke bot-wa: {e}")

    threading.Thread(target=_worker, daemon=True).start()
```
