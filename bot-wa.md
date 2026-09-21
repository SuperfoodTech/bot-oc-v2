# 📖 Dokumentasi & Handover Transfer Knowledge: WhatsApp Gateway Microservice (`bot-wa`)

> **Versi Rilis Baseline:** `v1.23.19`  
> **Status:** Production Ready  
> **Target Pengguna:** Tim Backend Engineer, DevOps / System Administrator, AI Agent Server FoodMaster.

---

## 1. Ringkasan Eksekutif & Tujuan Arsitektur

`bot-wa` adalah microservice independen berbasis **Node.js + Express + Baileys (@whiskeysockets/baileys)** yang bertugas mengelola sesi koneksi WhatsApp Multi-Device (MD) dan mengeksekusi pengiriman notifikasi buka/tutup toko secara otomatis ke nomor WhatsApp pemilik/owner Agency FoodMaster.

### Mengapa Dibuat Sebagai Microservice Terpisah?
1. **Isolasi Kegagalan (Fault Isolation):** Gangguan koneksi WhatsApp, reconnect socket, atau restart sesi QR tidak mempengaruhi container bot patroli Selenium (`fm-bot` & `fm-bot-vb`) dan web backend (`fm-backend`).
2. **Kepatuhan Zero-Downtime:** Bot patroli Selenium yang menjaga toko 24/7 tidak mengalami gangguan session browser saat dilakukan maintenance atau scan QR WhatsApp.
3. **Penyatuan UI (Unified Dashboard):** Halaman administrasi WhatsApp diintegrasikan langsung ke dalam Single Page Application (SPA) dashboard admin port utama (`admin_tab_wa.html`) tanpa wrapper `<iframe>` eksternal.

---

## 2. Diagram Arsitektur & Alur Notifikasi

```
+-----------------------------------------------------------------------------------+
|                            FOODMASTER SYSTEM ARCHITECTURE                         |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | [1] EVENT PATROLI BOT                                                       |  |
|  | main-bot (bot-oc) / main-vb (bot-vb) -> Eksekusi Buka/Tutup Toko Berhasil   |  |
|  +---------------------------------------+-------------------------------------+  |
|                                          |                                        |
|                                          v                                        |
|  +-----------------------------------------------------------------------------+  |
|  | [2] LAPIS 1 DEDUPLIKASI (Python Notifier - src/core/notifier.py)            |  |
|  | - Cek In-Memory Signature Hash (TTL 5 Menit)                                |  |
|  | - Jika baru -> Dispatch HTTP POST /api/v1/webhook/bot-action                |  |
|  +---------------------------------------+-------------------------------------+  |
|                                          |                                        |
|                                          v                                        |
|  +-----------------------------------------------------------------------------+  |
|  | [3] GATEWAY ENGINE (bot-wa Node.js Service - Port 3002)                    |  |
|  | - Verifikasi API Key (Header: X-API-Key)                                    |  |
|  | - Lapis 2 Dedup Cache (dedupKey TTL 5 Menit) & Queue Duplication Guard      |  |
|  | - Queue Worker Pacing (Jitter 2.5s - 4.5s) & Human Simulation ('composing') |  |
|  +---------------------------------------+-------------------------------------+  |
|                                          |                                        |
|                                          v                                        |
|  +-----------------------------------------------------------------------------+  |
|  | [4] WHATSAPP WEB MULTI-DEVICE (Baileys Engine)                              |  |
|  | -> Mengirim pesan terenkripsi ke WhatsApp Penerima (Owner Agency)           |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Konfigurasi Lingkungan (Environment Variables)

File konfigurasi runtime utama berada di `.env` (atau file `.env` di dalam subfolder `bot-wa/`):

| Variable | Default Value | Deskripsi |
| :--- | :--- | :--- |
| `PORT` | `3002` | Port HTTP internal service gateway WhatsApp |
| `WA_API_KEY` | `foodmaster-wa-secret-2026-key` | Token rahasia otentikasi API header `X-API-Key` |
| `WA_AUTH_DIR` | `./auth_info_baileys` | Path folder penyimpanan kredensial sesi multi-device Baileys |
| `GOOGLE_SHEETS_CSV_URL` | *URL Google Sheet CSV Agency* | URL publik export CSV Google Sheet database pemilik & nomor WhatsApp |
| `LOG_LEVEL` | `info` | Tingkat log Pino (`info`, `debug`, `warn`, `error`) |

---

## 4. Arsitektur Anti-Spam & Anti-Ban (Two-Tier Architecture)

Pengiriman pesan WhatsApp massal otomatis memiliki risiko *rate-limiting* atau *temporary ban*. Untuk mengatasinya, diterapkan arsitektur perlindungan 2 lapis:

### Lapis 1: Python Core In-Memory TTL Cache (`src/core/notifier.py`)
- Mencegah pengiriman webhook ganda yang dipicu oleh *transient patrol retry* atau multiple worker thread.
- Kunci signature: `MD5(phone + event_type + store_id + outlet_name)` dengan masa kedaluwarsa **5 menit**.

### Lapis 2: Gateway Engine Anti-Spam & Anti-Ban (`bot-wa/src/index.js`)
1. **Deduplication Key (`dedupKey`):** Mencegah pesan duplikat identik masuk ke antrean jika event yang sama datang dalam jendela 5 menit.
2. **Queue Deduplication:** Jika ada pesan dengan nomor dan isi yang persis sama masih mengantre di memory, tugas baru otomatis digabungkan (*deduplicated*).
3. **Queue Capacity Limit:** Antrean dibatasi maksimal **100 pesan** untuk mencegah kelebihan beban RAM (*OOM protection*).
4. **Humanized Typing Simulation (`composing`):** Sebelum pesan terkirim, bot memancarkan socket event `composing` (sedang mengetik) selama **800ms – 1600ms**, lalu kembali ke `paused`.
5. **Jitter Delay Pacing:** Jeda antar pesan diberikan variasi waktu acak aman **2.5 detik – 4.5 detik** (`2500ms + random(0..2000ms)`).

---

## 5. Format & Standarisasi Template Pesan

Template pesan WhatsApp diselaraskan **1:1** dengan format resmi Discord Webhook Agency, lengkap dengan hyperlink ShopeeFood per-outlet dan kontak CS FoodMaster.

### Contoh Pesan: Outlet Berhasil Dibuka (`ACTION_OPEN`)
```text
🟢 *OUTLET BERHASIL DIBUKA BOT*

Nama Outlet: *NAMA OUTLET MERCHANT*
Store ID: *12345678*
Lihat di ShopeeFood:
https://shopee.co.id/universal-link/now-food/shop/12345678

FoodMaster Bot Team
WA CS: wa.me/6285183151531
```

### Contoh Pesan: Outlet Berhasil Ditutup (`ACTION_CLOSE` / `ACTION_PAUSE`)
```text
🔴 *OUTLET BERHASIL DITUTUP BOT*

Nama Outlet: *NAMA OUTLET MERCHANT*
Store ID: *12345678*
Lihat di ShopeeFood:
https://shopee.co.id/universal-link/now-food/shop/12345678

FoodMaster Bot Team
WA CS: wa.me/6285183151531
```

---

## 6. Spesifikasi Kontrak REST API

Semua endpoint privat mewajibkan Header: `X-API-Key: <WA_API_KEY>`.

### 1. Health Check
- **Endpoint:** `GET /health`
- **Autentikasi:** Publik
- **Response:**
  ```json
  { "status": "ok", "service": "bot-wa-gateway", "timestamp": "2026-09-21T07:30:00.000Z" }
  ```

### 2. WhatsApp Live Status & QR Code
- **Endpoint:** `GET /api/v1/status`
- **Autentikasi:** Publik (Diproteksi di layer reverse-proxy / dashboard session)
- **Response:**
  ```json
  {
    "success": true,
    "wa_status": "CONNECTED", // INITIALIZING | QR_READY | CONNECTING | CONNECTED | DISCONNECTED
    "qr_code_raw": null,
    "qr_code_image": "data:image/png;base64,...",
    "user": {
      "name": "Admin FoodMaster",
      "phone": "081234567890",
      "id": "6281234567890:1@s.whatsapp.net"
    },
    "queue_length": 0
  }
  ```

### 3. Sinkronisasi Data Pemilik dari Google Sheet
- **Endpoint:** `POST /api/v1/sync-sheet`
- **Autentikasi:** Publik / Admin
- **Deskripsi:** Memaksa refresh parsing data CSV Google Sheet secara langsung (*bypassing cache 5 menit*).
- **Response:**
  ```json
  {
    "success": true,
    "message": "Data Google Sheet Agency berhasil disinkronkan.",
    "total_owners": 35,
    "total_outlets": 112,
    "data": [ ... ]
  }
  ```

### 4. Kirim Pesan Webhook Patroli Bot
- **Endpoint:** `POST /api/v1/webhook/bot-action`
- **Autentikasi:** `X-API-Key`
- **Payload:**
  ```json
  {
    "phone": "081234567890",
    "merchant_name": "Merchant ABC",
    "outlet_name": "Outlet ABC Cabang 1",
    "store_id": "98765432",
    "event_type": "ACTION_OPEN"
  }
  ```
- **Response:**
  ```json
  {
    "success": true,
    "message": "Webhook diterima dan notifikasi WA diproses.",
    "event_type": "ACTION_OPEN",
    "deduplicated": false
  }
  ```

### 5. Putus Sesi (Logout & Reset Auth)
- **Endpoint:** `POST /api/v1/logout`
- **Autentikasi:** `X-API-Key`
- **Deskripsi:** Melakukan logout dari socket Baileys, menghapus file di `auth_info_baileys/`, dan otomatis merestart listener untuk memunculkan QR Code baru.

---

## 7. Panduan Deployment & Pengelolaan Systemd

Microservice `bot-wa` dikelola sebagai service systemd independen di Linux Host Server agar auto-start saat reboot dan auto-restart saat crash.

### A. Instalasi & Setup Otomatis
Jalankan skrip installer dari root project:
```bash
bash systemd/setup.sh
```

### B. Perintah Operasional Systemctl
```bash
# Menjalankan service WhatsApp Gateway
sudo systemctl start bot-wa

# Mematikan service
sudo systemctl stop bot-wa

# Restart service (misal setelah ganti API key / port)
sudo systemctl restart bot-wa

# Melihat status aktif service
sudo systemctl status bot-wa

# Mengaktifkan auto-start saat server boot
sudo systemctl enable bot-wa
```

### C. Pemantauan Log Real-Time (Journalctl)
```bash
journalctl -u bot-wa -f -n 50
```

---

## 8. Panduan Troubleshooting Server Agent

### 1. Status Menampilkan `QR_READY` tapi QR Code Tidak Muncul di Dashboard
- Buka dashboard Admin FoodMaster -> Tab **WhatsApp Gateway**.
- Klik tombol **Muat Ulang QR** di bawah canvas.
- Jika masih blank, periksa log dengan `journalctl -u bot-wa -f` atau cek status backend proxy `/api/v1/wa/status`.

### 2. Session Terputus (`DISCONNECTED` / `Logged Out`)
- Terjadi jika user menekan tombol "Tautkan Perangkat Lain" atau me-logout sesi dari menu WhatsApp di HP.
- **Solusi:** Klik tombol **Putus Sesi** di dashboard Admin -> Konfirmasi di modal kustom -> Scan QR Code baru yang muncul di layar.

### 3. Pesan Tidak Terkirim ke Nomor Tertentu
- **Penyebab:** Format nomor salah (misal: mengandung tanda hubung, spasi, atau bukan nomor WhatsApp aktif).
- Fungsi `normalizePhoneNumber` otomatis mengubah awalan `08xxx` / `8xxx` menjadi format internasional `628xxx`. Pastikan nomor di Google Sheet valid.

### 4. Menghapus Manual Sesi Autentikasi (Hard Reset)
Jika service mengalami *auth lock* yang tidak dapat pulih:
```bash
sudo systemctl stop bot-wa
rm -rf /home/akbarhann/project/bot-oc/bot-wa/auth_info_baileys/*
sudo systemctl start bot-wa
```
Sistem akan langsung men-generate sesi baru dan siap untuk scan QR.

---
*Dokumentasi ini dibuat untuk menjamin kelancaran serah terima operasional (Handover Knowledge) antar tim engineering & AI Server Agent FoodMaster.*
