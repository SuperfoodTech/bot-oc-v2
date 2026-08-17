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

## Aturan Pencatatan Versi Update (Semantic Versioning)

Setiap generasi kode atau penambahan fitur baru wajib membuat file dokumentasi rilis baru di dalam folder `update/<MAJOR>.<MINOR>.<PATCH>.md` mengikuti standar Semantic Versioning (`MAJOR.MINOR.PATCH`):
- **MAJOR**: Perubahan arsitektur besar / breaking changes.
- **MINOR**: Penambahan fitur baru yang kompatibel.
- **PATCH/FIX**: Perbaikan bug, optimasi handling error, atau patch stabilitas.
Setiap file update wajib mencantumkan seksi `Whats New`, `Spesifikasi`, dan `Handling`.

## Aturan Gaya Penulisan & Komunikasi (Copywriting & Dokumentasi)

1. **Penggunaan Emoji**:
   - Dilarang menggunakan emoji secara berlebihan (*excessive emojis*) pada teks respons, penjelasan, maupun dokumentasi rilis.
   - Gunakan gaya penulisan yang lugas, profesional, dan langsung pada inti teknis.

2. **Fakta Kode & Relevansi (Strict Project Relevance)**:
   - Dilarang mengarang fitur, membuat asumsi fiktif, atau menuliskan sesuatu yang tidak ada di dalam codebase project ini.
   - Seluruh penjelasan, analisis, dan dokumentasi rilis harus 100% akurat dan benar-benar terverifikasi (*strictly related*) dengan kode yang ada.


