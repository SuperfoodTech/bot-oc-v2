# Microservice `bot-wa` (WhatsApp Gateway)

Microservice berbasis **Node.js + Baileys + Express** untuk mengirimkan notifikasi aksi bot patroli (`bot-oc` & `bot-vb`) langsung ke WhatsApp Merchant secara otomatis, ringan, dan terisolasi.

---

## 📁 Struktur Direktori `bot-wa`

```text
bot-wa/
├── src/
│   └── index.js           # Main Express server & Baileys socket handler
├── .env.example           # Template konfigurasi environment
├── ARCHITECTURE.md        # Dokumen arsitektur microservices terpisah
├── CONTRACT.md            # Spesifikasi Kontrak Backend API Webhook
├── Dockerfile             # Dockerfile container build
├── docker-compose.yml     # Standalone Docker Compose configuration
└── package.json           # Node.js dependencies
```

---

## 🚀 Panduan Deploy di Server Terpisah

### Langkah 1: Pindahkan Folder `bot-wa` ke Server WhatsApp

Pindahkan folder `bot-wa` ke server baru menggunakan `scp`, `rsync`, atau Git repository:

```bash
scp -r bot-wa user@ip-server-wa:/home/user/
```

### Langkah 2: Konfigurasi Environment

Di server WhatsApp, masuk ke folder `bot-wa` dan buat file `.env`:

```bash
cd bot-wa
cp .env.example .env
```

Edit file `.env` dan atur `WA_API_KEY` rahasia Anda:
```env
PORT=3002
WA_API_KEY=rahasia-api-key-wa-gateway-12345
LOG_LEVEL=info
```

### Langkah 3: Jalankan Service via Docker Compose (Recommended)

Jalankan container secara daemon:

```bash
docker compose up -d --build
```

---

## 📲 Panduan Scan QR Code WhatsApp

Setelah container berjalan di Server WhatsApp, cek log container untuk melakukan Scan QR:

```bash
docker compose logs -f
```

Atau jika dijalankan secara manual (`npm start`):
1. Buka aplikasi WhatsApp di Smartphone Anda.
2. Masuk ke **Menu (Titik tiga / Pengaturan)** -> **Perangkat Tertaut (Linked Devices)** -> **Tautkan Perangkat (Link a Device)**.
3. Arahkan kamera HP ke QR Code yang muncul di terminal konsol server.
4. Setelah terhubung, status akan berubah menjadi `CONNECTED`.

---

## 🧪 Menguji Webhook

Anda dapat menguji kirim notifikasi ke nomor WhatsApp Anda sendiri menggunakan `curl`:

```bash
curl -X POST http://localhost:3002/api/v1/webhook/bot-action \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rahasia-api-key-wa-gateway-12345" \
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

## 🔗 Hubungkan dengan Server Bot OC / Bot VB

Di Server Bot OC & Bot VB (`bot-oc` / `bot-vb`), tambahkan variabel berikut pada `.env` server bot:

```env
WA_GATEWAY_URL=http://<IP_SERVER_WA>:3002
WA_GATEWAY_KEY=rahasia-api-key-wa-gateway-12345
```
