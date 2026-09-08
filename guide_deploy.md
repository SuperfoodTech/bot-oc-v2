# Panduan Deployment Server: Migrasi dari Docker ke Systemd (Native)

Dokumen ini berisi panduan lengkap langkah demi langkah untuk menonaktifkan container `fm-bot` dan `fm-bot-vb` di Docker serta mengalihkan runtime bot patroli ke **Systemd (Native Linux Service)** di server.

---

## Ringkasan Arsitektur

| Komponen | Runtime yang Direkomendasikan | Port / Socket | Service Name |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | Docker (`fm-postgres`) atau Native Host | `5432` / `5435` | `docker compose up -d db` |
| **Web Backend / UI** | Docker (`fm-backend`) atau Systemd | `3001` | `bot-web.service` atau `web` container |
| **Bot-OC Daemon** | **Systemd (Native)** | API `8081` | `bot-oc.service` |
| **Bot-VB Daemon** | **Systemd (Native)** | API `8082` | `bot-vb.service` |

---

## Langkah 1: Menonaktifkan Service Bot di Docker

Agar tidak terjadi bentrok session login, port `8081`, maupun database lock, hentikan container bot di Docker Compose.

### 1.1 Hentikan dan Hapus Container Bot
Jalankan perintah berikut di folder project server:

```bash
# 1. Hentikan container fm-bot dan fm-bot-vb
docker compose stop bot bot-vb

# 2. Hapus container agar tidak auto-start saat Docker restart
docker compose rm -f bot bot-vb
```

### 1.2 (Opsional) Memastikan Container Tidak Pernah Berjalan Otomatis di Docker
Jika Anda ingin `docker compose up -d` di masa mendatang hanya menjalankan database `db` dan `web` tanpa menjalankan bot:

Gunakan perintah compose dengan menentukan service:
```bash
docker compose up -d db web
```
*(Atau hanya `docker compose up -d db` jika backend `web` juga dijalankan via systemd).*

---

## Langkah 2: Persiapan Dependensi di Host Server Linux

Karena Selenium & Chrome akan berjalan langsung di host Linux, pastikan paket pendukung sudah terpasang.

### 2.1 Pasang Google Chrome Stable
```bash
sudo apt update
sudo apt install -y wget curl ca-certificates libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2

# Download dan pasang Google Chrome Stable
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
rm google-chrome-stable_current_amd64.deb

# Verifikasi instalasi Chrome
google-chrome --version
```

### 2.2 Pasang `uv` (Fast Python Package & Project Manager)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# Verifikasi instalasi uv
uv --version
```

### 2.3 Sinkronisasi Virtual Environment & Dependensi Project
Di dalam direktori project:
```bash
# Install dependensi project utama
uv sync

# Install dependensi virtual brand jika diperlukan
cd main-vb && uv sync && cd ..
```

---

## Langkah 3: Konfigurasi File Lingkungan (`.env`)

Pastikan file `.env` di root direktori project sudah berisi konfigurasi database dan kredensial Shopee yang valid:

```env
# Database (Jika PostgreSQL tetap di Docker, gunakan localhost:5435 atau port Postgres aktif)
DATABASE_URL=postgresql://foodmaster:password_rahasia@127.0.0.1:5435/foodmaster

# Kredensial & Bot Settings
SHOPEE_BOT_USERNAME=auto7313
SHOPEE_BOT_PASSWORD=PasswordShopeeAnda
ALLOWED_USERNAMES=auto7313

# Runtime Mode
HEADLESS=true
TZ=Asia/Jakarta

# Webhook & Integrasi (Opsional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## Langkah 4: Setup & Aktivasi Systemd Service

Gunakan script setup otomatis yang telah disediakan:

```bash
# 1. Berikan izin eksekusi script
chmod +x systemd/setup.sh

# 2. Jalankan installer service
./systemd/setup.sh
```

Script ini akan secara otomatis:
- Menyesuaikan user pemilik proses (`whoami`), path project, dan path binary `uv`.
- Memasang unit service ke `/etc/systemd/system/bot-oc.service`, `bot-vb.service`, dan `bot-web.service`.
- Menjalankan `systemctl daemon-reload`.

---

## Langkah 5: Menjalankan Service & Mengaktifkan Auto-Start

### 5.1 Jalankan Service
```bash
# Jalankan Bot O/C (Agency/Reguler)
sudo systemctl start bot-oc

# Jalankan Bot Virtual Brand (VB)
sudo systemctl start bot-vb

# (Opsional) Jalankan Web Backend jika tidak pakai Docker
sudo systemctl start bot-web
```

### 5.2 Aktifkan Auto-Start saat Server Boot
```bash
sudo systemctl enable bot-oc bot-vb
sudo systemctl enable bot-web  # jika web backend via systemd
```

---

## Langkah 6: Verifikasi & Monitoring

### 6.1 Cek Status Service
```bash
sudo systemctl status bot-oc
sudo systemctl status bot-vb
```

Status harus menunjukkan **`active (running)`**.

### 6.2 Cek Real-Time Log
```bash
# Log Bot O/C
journalctl -u bot-oc -f

# Log Bot Virtual Brand
journalctl -u bot-vb -f

# Log gabungan Bot O/C dan Bot VB
journalctl -u bot-oc -u bot-vb -f --lines=50
```

---

## Langkah 7: Perintah Operasional Sehari-hari

### Restart Service (Saat Ada Update Kode / Config)
```bash
# Restart bot O/C
sudo systemctl restart bot-oc

# Restart bot VB
sudo systemctl restart bot-vb

# Restart Web API (tanpa mengganggu bot)
sudo systemctl restart bot-web
```

### Menghentikan Sementara Service
```bash
sudo systemctl stop bot-oc
sudo systemctl stop bot-vb
```

---

## Troubleshooting & FAQ

### 1. Pesan `Socket lock check: Port 8081 is already in use`
- **Penyebab**: Masih ada proses bot lama atau container Docker yang berjalan dan menggunakan port 8081.
- **Solusi**:
  ```bash
  # Cek proses yang memakai port 8081 / 8082
  sudo lsof -i :8081
  sudo lsof -i :8082
  
  # Matikan container docker lama jika masih aktif
  docker compose stop bot bot-vb
  ```

### 2. Chrome Profile Lock (`SingletonLock`)
- **Penyebab**: Proses Chrome sebelumnya terhenti mendadak dan meninggalkan file lock di folder data.
- **Solusi**:
  ```bash
  sudo systemctl stop bot-oc bot-vb
  rm -f src/data/chrome_profile*/Singleton*
  rm -f main-bot/src/daemon.lock main-vb/src/daemon.lock
  sudo systemctl start bot-oc bot-vb
  ```

### 3. Database Connection Refused
- Pastikan container database PostgreSQL di Docker aktif:
  ```bash
  docker compose ps
  docker compose up -d db
  ```
- Periksa port mapping pada `.env` (default `127.0.0.1:5435`).
