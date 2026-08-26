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

Baseline version project dimulai dari `1.0.0`.

Latest documented release: `1.10.1`.

Service `bot-vb` wajib menggunakan `HEADLESS=true` pada deployment Docker.
Jangan menambahkan release yang mengubahnya ke `false`, karena server tidak
memiliki display/X server dan Chrome akan gagal start.

Runtime VB bersifat pure toggle setelah gate jadwal: `penangguhan` dan masa
aktif layanan tidak boleh memaksa action VB. Pengecualian ini harus berada di
adapter decision VB, bukan mengubah worker bot-OC.

`bot-vb` pada deployment server wajib tetap `HEADLESS=true`; jangan mengubah
konfigurasi service server menjadi mode GUI.

`main-vb/src/daemon.py` harus memanggil `sync_all_stores` dari worker VB yang
identik dengan bot-OC; jangan mengembalikan API `patrol_once` ke worker.

Build Docker wajib mengecualikan seluruh `src/data/**` dari build context.
Credential, session, dan Chrome profile adalah data runtime yang dipasang
melalui volume, bukan bagian image.

`main-vb/src/core/browser.py` wajib identik byte-for-byte dengan
`src/core/browser.py`. Perbedaan runtime hanya boleh melalui environment
variable `VB_CREDENTIALS_FILE`, `VB_SESSION_FILE`,
`VB_CHROME_PROFILE_DIR`, dan `VB_CHROME_PROFILE_NAME`.

`main-vb/src/worker.py` wajib identik byte-for-byte dengan
`main-bot/src/worker.py`. Perbedaan VB harus berada di adapter `main-vb/src/db.py`
dan konfigurasi runtime: target toggle dibaca dari `vb_brands.applied_status`,
sedangkan Sheet hanya dipakai untuk import scope brand.

Normalisasi live status VB wajib sama dengan Bot O/C: gunakan
`pause_info.pause_start_time > 0` untuk `PAUSE`, `status_str == OPEN` untuk
`ON`, dan status non-OPEN tanpa pause aktif sebagai `CLOSED`.

Bot VB wajib meneruskan `pause_until` brand yang sudah diterapkan ke payload
pause XHR Shopee sebagai `pause_end_time` Unix milliseconds; tidak boleh
memakai fallback 1 hari ketika target waktu tersedia.

Perhitungan pause `rest_of_day` wajib menggunakan objek datetime timezone-aware
Asia/Jakarta sebelum dikonversi menjadi Unix timestamp milliseconds.

Sheet VB menjadi source of truth untuk scope brand: setiap brand yang tidak
ada pada hasil fetch terbaru harus ditandai `is_active=false`, bukan dibiarkan
aktif dari import sebelumnya.

Published tab Google Sheet Virtual Brand menggunakan `gid=401458905`.

Import VB wajib memperlakukan kolom `Status` sebagai import gate yang
konsisten dengan Bot O/C. Hanya nilai `Aktif` (case-insensitive) yang
memasukkan brand ke scope; nilai lain menonaktifkan brand dari dashboard dan
patrol tanpa menganggap kolom tersebut sebagai Store ID.

Konfigurasi `HEADLESS` dipusatkan di `.env` dan dibaca bersama oleh service
`bot-oc` serta `bot-vb` melalui Docker Compose. Nilai default tetap `true`
agar stabil pada server/container tanpa X display.

Setiap update kode, konfigurasi, atau perilaku aplikasi wajib:

1. Membuat atau memperbarui dokumentasi rilis di folder `/update`.
2. Mencatat aturan atau perubahan penting yang memengaruhi pekerjaan berikutnya di `AGENTS.md`.
3. Memilih nomor versi berdasarkan jenis perubahan, bukan sekadar menaikkan angka patch secara berurutan:
   - **MAJOR** (`1.x.x`): breaking changes, perubahan kontrak API, migrasi yang tidak kompatibel, atau perubahan arsitektur besar.
   - **MINOR** (`x.1.x`): fitur baru yang kompatibel dengan perilaku/API sebelumnya.
   - **PATCH** (`x.x.1`): bug fix, perbaikan kecil, optimasi handling error, atau patch stabilitas yang tidak mengubah kontrak.
4. Jika sebuah perubahan termasuk breaking atau feature, jangan menuliskannya sebagai patch hanya karena update sebelumnya memakai nomor patch. Nomor versi harus mencerminkan dampak perubahan.

File update wajib menggunakan format `update/<MAJOR>.<MINOR>.<PATCH>.md` dan mencantumkan seksi `Whats New`, `Spesifikasi`, dan `Handling`.

## Aturan Gaya Penulisan & Komunikasi (Copywriting & Dokumentasi)

1. **Penggunaan Emoji**:
   - Dilarang menggunakan emoji secara berlebihan (*excessive emojis*) pada teks respons, penjelasan, maupun dokumentasi rilis.
   - Gunakan gaya penulisan yang lugas, profesional, dan langsung pada inti teknis.

2. **Fakta Kode & Relevansi (Strict Project Relevance)**:
   - Dilarang mengarang fitur, membuat asumsi fiktif, atau menuliskan sesuatu yang tidak ada di dalam codebase project ini.
   - Seluruh penjelasan, analisis, dan dokumentasi rilis harus 100% akurat dan benar-benar terverifikasi (*strictly related*) dengan kode yang ada.
