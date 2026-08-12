# 🚀 FoodMaster Bot-OC: Server Setup & Deployment Guide for AI Agents

Guide ini dirancang secara khusus untuk **AI Agent** yang mengeksekusi perintah CLI secara otonom di server Linux (Ubuntu/Debian) untuk mengonfigurasi, membangun, dan mendeploy layanan **FoodMaster (Web Backend & Shopee Automation Daemon)**.

---

## 📌 1. Overview Arsitektur Sistem

Proyek ini terdiri dari 3 komponen utama:
1. **PostgreSQL Database** (`db`): Menyimpan data toko, log operasional, jadwal, dan status bot.
2. **FastAPI Web Application** (`web`): Backend REST API & Admin/User Dashboard (Port `3001`).
3. **Shopee Automation Patrol Daemon** (`bot`): Daemon 24/7 yang menjalankan Selenium Chromium headless untuk melakukan Auto-Open / Auto-Pause toko Shopee.

---

## ⚙️ 2. Prasyarat Sistem & Dependensi Server

Sebelum menjalankan deployment, AI Agent harus memastikan dependensi dasar telah terinstal di server.

### Eksekusi Perintah Cek Sistem:
```bash
# 1. Cek ketersediaan Docker & Docker Compose
docker --version && docker compose version

# 2. Jika Docker belum ada, install via script resmi (Ubuntu/Debian):
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

---

## 🔑 3. Konfigurasi Environment (`.env`)

AI Agent harus membuat file `.env` di akar repositori (`/path/to/project/.env`).

### Perintah Pembuatan File `.env`:
```bash
cat << 'EOF' > .env
# Database Settings
POSTGRES_DB=foodmaster
POSTGRES_USER=foodmaster
POSTGRES_PASSWORD=SecurePassword123!
DATABASE_URL=postgresql://foodmaster:SecurePassword123!@db:5432/foodmaster

# Application Settings
ENVIRONMENT=production
PORT=3001
APP_BASE_URL=http://localhost:3001

# Shopee Bot Whitelist & Credentials
ALLOWED_USERNAMES=auto7313
SHOPEE_BOT_USERNAME=auto7313
SHOPEE_BOT_PASSWORD=Auto@7313

# Browser Engine
HEADLESS=true
EOF
```

---

## 🛠️ 4. Opsi Deployment Utama: Docker Compose (Direkomendasikan)

Metode ini paling aman dan konsisten karena membungkus Chromium & driver secara terisolasi.

### Step 1: Jalankan Production Build & Deploy Script
```bash
chmod +x ./scripts/prod.sh
./scripts/prod.sh
```

*Atau eksekusi langsung via Docker Compose BuildKit:*
```bash
DOCKER_BUILDKIT=1 docker compose -f docker-compose.yml -p fm up -d --build
```

### Step 2: Cek Status Container
```bash
docker compose -p fm ps
```
Pastikan 3 container berstatus **Up / Running**:
- `fm-postgres`
- `fm-backend`
- `fm-bot`

### ⚡ Step 3: Zero-Downtime Update Khusus Backend/Frontend Web (Non-Bot Updates)
Jika perubahan kode hanya berada di `src/backend/`, template HTML, CSS/JS static, atau route REST API web (tidak merubah core bot), **wajib** menggunakan perintah berikut agar container bot (`fm-bot`) **tidak ikut terhenti / terputus**:

```bash
# Rebuild & restart HANYA service web tanpa mengganggu container bot & postgres
docker compose build web
docker compose up -d --no-deps web
```
*Catatan: Parameter `--no-deps` memastikan container bot dan database tetap aktif berjalan 24/7.*

---

## 🖥️ 5. Opsi Deployment Alternatif: Bare-Metal (Tanpa Docker / Systemd)

Jika server tidak menggunakan Docker, AI Agent dapat melakukan setup langsung di OS Host.

### Step 1: Install Package & Headless Chromium
```bash
sudo apt-get update && sudo apt-get install -y \
    python3.12 python3.12-venv python3-pip \
    chromium-browser chromium-chromedriver \
    curl wget ca-certificates
```

### Step 2: Install UV Package Manager & Sync Dependencies
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env || true

# Sync virtualenv
uv sync --frozen --no-dev
```

### Step 3: Buat Layanan Systemd (`fm-web.service` & `fm-bot.service`)

**1. Service Backend Web:** `/etc/systemd/system/fm-web.service`
```ini
[Unit]
Description=FoodMaster Web Backend Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/bot-oc
ExecStart=/path/to/bot-oc/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 3001
Restart=always
Environment=PYTHONPATH=/path/to/bot-oc/src
Environment=PORT=3001
Environment=HEADLESS=true

[Install]
WantedBy=multi-user.target
```

**2. Service Bot Daemon:** `/etc/systemd/system/fm-bot.service`
```ini
[Unit]
Description=FoodMaster Bot Patrol Daemon
After=network.target fm-web.service

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/bot-oc
ExecStart=/path/to/bot-oc/.venv/bin/python main-bot/src/daemon.py
Restart=always
Environment=PYTHONPATH=/path/to/bot-oc/src
Environment=HEADLESS=true
Environment=CHROMEDRIVER_PATH=/usr/bin/chromedriver
Environment=CHROME_BIN=/usr/bin/chromium

[Install]
WantedBy=multi-user.target
```

**Reload & Start Systemd:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fm-web fm-bot
```

---

## 🧪 6. Verifikasi Otonom & Health Check (Wajib Dilakukan AI Agent)

AI Agent **wajib** menjalankan tes berikut setelah deployment untuk memastikan semua sistem berjalan 100%:

### 1. Verification Test Script
```bash
# Cek HTTP Health Check
curl -s -f http://localhost:3001/api/v1/health | grep -q "status" && echo "✅ Web Backend Online" || echo "❌ Web Backend Fail"

# Cek Bot Patrol Status
curl -s http://localhost:3001/api/v1/admin/bot-status
```

### 2. Cek Real-Time Logs Container
```bash
# Web Logs
docker compose -p fm logs --tail=30 web

# Bot Patrol Daemon Logs
docker compose -p fm logs --tail=30 bot
```

---

## ⚠️ 7. Troubleshooting & Handling Stale Lock

1. **Kasus: Daemon Tidak Mau Jalan (Stale Lock)**
   Jika daemon terhenti mendadak dan menyisakan file lock:
   ```bash
   rm -f main-bot/src/daemon.lock
   docker compose -p fm restart bot
   ```

2. **Kasus: Selenium Chromium Error (No Sandbox)**
   Semua script browser di `src/core/browser.py` sudah terkonfigurasi `--no-sandbox` dan `--disable-dev-shm-usage` untuk kompatibilitas container Linux.

3. **Restart Total Layanan:**
   ```bash
   ./scripts/prod.sh
   ```
