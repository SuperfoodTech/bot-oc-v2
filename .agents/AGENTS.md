# Aturan Deployment & Pengelolaan Service Bot-OC

## Aturan Update Backend & Frontend (Non-Bot Updates)

Setiap update kode yang **TIDAK** berhubungan secara langsung dengan logika bot patroli (misalnya perubahan pada file `src/backend/`, template HTML, CSS/JS static, atau route REST API Web):

1. **Wajib Menggunakan Zero-Downtime Deployment Command**:
   Dilarang menggunakan `./scripts/prod.sh` atau `docker compose down` untuk update non-bot karena akan mematikan container bot dan menginterupsi session Selenium browser yang sedang berjalan.

2. **Perintah Standar Update Web Backend/Frontend**:
   ```bash
   docker compose build web
   docker compose up -d --no-deps web
   ```
   - Parameter `--no-deps` wajib disertakan agar Docker Compose hanya me-restart container `fm-backend` (`web`), dan membiarkan container `fm-bot` serta `fm-postgres` tetap aktif 24/7 tanpa interruption.

3. **Kapan Bot Boleh / Wajib Di-rebuild**:
   Container `fm-bot` hanya boleh di-rebuild/di-restart jika:
   - Ada perubahan pada modul shared/core: `src/core/` (seperti `browser.py`, `decision.py`) atau `src/shopee/`.
   - Ada migrasi skema tabel/kolom database PostgreSQL baru.
   - Ada penambahan dependensi Python baru di `pyproject.toml` / `uv.lock`.
