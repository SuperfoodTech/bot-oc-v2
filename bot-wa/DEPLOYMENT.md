# Standalone Deployment & Agent Build Guide - `bot-wa` (WhatsApp Gateway)

Dokumen ini berisi panduan teknis langkah-demi-langkah bagi Agent AI atau Engineer yang bertugas melakukan **build, deploy, dan mengkonfigurasi microservice `bot-wa` di server terpisah**.

---

## 1. Prasyarat Server (Prerequisites)

- **OS**: Linux (Ubuntu 20.04/22.04 LTS, Debian, AlmaLinux, atau RHEL).
- **Node.js**: v18.x atau v20.x LTS (jika tanpa Docker).
- **Docker & Docker Compose**: v24+ (opsi direkomendasikan).
- **Network**: Port `3002` terbuka di firewall (atau via Reverse Proxy Nginx).

---

## 2. Struktur File & Pembawaan Bahan

Pastikan seluruh file berikut berada di dalam folder `/home/user/bot-wa`:

```text
bot-wa/
├── src/
│   └── index.js           # Express API & Baileys Client Engine
├── .env.example           # Template environment variables
├── Dockerfile             # Container build recipe (Node 20 Alpine)
├── docker-compose.yml     # Standalone Docker orchestration
├── ARCHITECTURE.md        # Arsitektur & Sequence Diagram
├── CONTRACT.md            # Kontrak REST API Webhook JSON Schema
├── DEPLOYMENT.md          # Dokumen ini (Agent Build Guide)
├── README.md              # Panduan singkat pengguna
└── package.json           # Node.js manifest & dependencies
```

---

## 3. Metode Deployment 1: Menggunakan Docker Compose (Direkomendasikan)

### Langkah 3.1: Copy & Konfigurasi `.env`

```bash
cd /home/user/bot-wa
cp .env.example .env
```

Edit file `.env`:
```env
PORT=3002
WA_API_KEY=GANTI_DENGAN_SECRET_API_KEY_ANDA_12345
WA_AUTH_DIR=/app/auth_info_baileys
LOG_LEVEL=info
```

### Langkah 3.2: Build & Start Container

```bash
docker compose up -d --build
```

### Langkah 3.3: Scan QR Code Login WhatsApp

Periksa log container untuk menampilkan QR Code pada konsol:

```bash
docker compose logs -f
```

1. Buka aplikasi WhatsApp di Smartphone.
2. Pilih **Menu** -> **Perangkat Tertaut (Linked Devices)** -> **Tautkan Perangkat (Link a Device)**.
3. Arahkan kamera HP ke QR Code yang tercetak di konsol terminal log.
4. Setelah terhubung, status log akan berubah menjadi: `Koneksi WhatsApp BERHASIL terhubung 24/7!`.

---

## 4. Metode Deployment 2: Menggunakan Systemd / PM2 (Tanpa Docker)

### Langkah 4.1: Install Dependencies

```bash
cd /home/user/bot-wa
npm install --production
```

### Langkah 4.2: Jalankan via PM2

```bash
npm install -g pm2
pm2 start src/index.js --name "bot-wa-gateway"
pm2 save
pm2 startup
```

### Langkah 4.3: Scan QR Code via PM2 Logs

```bash
pm2 logs bot-wa-gateway
```

---

## 5. Verifikasi & Pengujian Health Check

### 5.1 Cek Health Check Endpoint

```bash
curl http://localhost:3002/health
```
Response:
```json
{
  "status": "ok",
  "service": "bot-wa-gateway",
  "timestamp": "2026-09-16T15:45:00.000Z"
}
```

### 5.2 Cek Status Koneksi WhatsApp

```bash
curl -H "X-API-Key: GANTI_DENGAN_SECRET_API_KEY_ANDA_12345" http://localhost:3002/api/v1/status
```
Response saat terhubung:
```json
{
  "success": true,
  "wa_status": "CONNECTED",
  "qr_code_raw": null,
  "queue_length": 0
}
```

### 5.3 Tes Kirim Webhook Notifikasi (Simulation)

```bash
curl -X POST http://localhost:3002/api/v1/webhook/bot-action \
  -H "Content-Type: application/json" \
  -H "X-API-Key: GANTI_DENGAN_SECRET_API_KEY_ANDA_12345" \
  -d '{
    "phone": "6281234567890",
    "event_type": "ACTION_OPEN",
    "platform": "Shopee",
    "merchant_name": "Kopi Mantap",
    "outlet_name": "Cabang Sudirman",
    "store_id": "22403325"
  }'
```

---

## 6. Integrasi dengan Server Bot Patroli (`bot-oc`)

Di server tempat `bot-oc` berada, tambahkan environment variabel berikut pada `.env` atau systemd service:

```env
WA_GATEWAY_URL=http://<IP_SERVER_WA_GATEWAY>:3002
WA_GATEWAY_KEY=GANTI_DENGAN_SECRET_API_KEY_ANDA_12345
```

---

## 7. Troubleshooting & Recovery Guide

| Kendala | Penyebab | Solusi |
| :--- | :--- | :--- |
| **HTTP 401 Unauthorized** | Header `X-API-Key` tidak sesuai dengan `.env` | Samakan nilai `WA_API_KEY` di server WA dan client `bot-oc`. |
| **Status `DISCONNECTED`** | Sesi di-logout dari HP atau expired | Hapus isi folder `auth_info_baileys` (atau docker volume `wa_session_data`) lalu restart service untuk scan QR ulang. |
| **Pesan Terlambat Terkirim** | Message Queue Throttling (Anti-Ban) | Sistem menerapkan delay 1.5 detik per pesan demi keamanan nomor. Ini adalah perilaku normal (*by design*). |
