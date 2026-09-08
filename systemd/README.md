# Panduan Setup Systemd (Native Deployment) FoodMaster

Panduan ini digunakan untuk menjalankan service **Bot-OC** (`main-bot`), **Bot-VB** (`main-vb`), dan **Web Backend** langsung di Linux Server host menggunakan Systemd dan `uv` tanpa Docker.

---

## 1. Prasyarat di Server

1. **Python & `uv`**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source $HOME/.cargo/env
   ```
2. **Google Chrome Stable** (wajib untuk browser automation):
   ```bash
   wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
   sudo apt update && sudo apt install -y ./google-chrome-stable_current_amd64.deb
   ```
3. **PostgreSQL**:
   - Berjalan lokal di server (`sudo apt install postgresql`) atau via Docker container kecil khusus database.
   - Pastikan variabel `DATABASE_URL` di file `.env` mengarah ke database PostgreSQL yang aktif.

---

## 2. Instalasi Cepat Otomatis

Jalankan script installer dari direktori project:
```bash
./systemd/setup.sh
```
Script ini akan:
- Mendeteksi user sistem, lokasi folder project, dan path binary `uv`.
- Men-generate file unit service ke `/etc/systemd/system/`.
- Menjalankan `sudo systemctl daemon-reload`.

---

## 3. Manajemen Service

| Perintah | Deskripsi |
| :--- | :--- |
| `sudo systemctl start bot-oc` | Menjalankan daemon Bot O/C (Agency/Reguler) |
| `sudo systemctl start bot-vb` | Menjalankan daemon Bot VB (Virtual Brand) |
| `sudo systemctl start bot-web` | Menjalankan Web Backend & API (port 3001) |
| `sudo systemctl enable bot-oc bot-vb bot-web` | Mengaktifkan auto-start saat server boot |
| `sudo systemctl restart bot-oc` | Me-restart service bot-oc |
| `sudo systemctl stop bot-oc` | Menghentikan service bot-oc |
| `sudo systemctl status bot-oc` | Memeriksa status service bot-oc |

---

## 4. Monitoring Log (Real-time)

```bash
# Log Bot O/C
journalctl -u bot-oc -f

# Log Bot Virtual Brand
journalctl -u bot-vb -f

# Log Web Backend
journalctl -u bot-web -f

# Log gabungan semua service
journalctl -u bot-oc -u bot-vb -u bot-web -f
```

---

## 5. Konfigurasi Port & Isolasi

- **Bot O/C API**: port `8081` (`BOT_API_PORT=8081`)
- **Bot VB API**: port `8082` (`BOT_API_PORT=8082`)
- **Web App**: port `3001` (`PORT=3001`)
- **Headless Mode**: `HEADLESS=true` diaktifkan secara default di kedua service bot.
