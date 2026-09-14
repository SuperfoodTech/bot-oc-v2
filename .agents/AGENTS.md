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

Latest documented release: `1.13.9`.

Sinkronisasi nama outlet asli (`data.store.name`) dari API Shopee Foody pada
menu Business Hours disimpan ke kolom `outlets.long_name` khusus untuk Virtual Brand (VB)
melalui adapter `main-vb/src/db.py`, sedangkan `src/backend/db.py` menyediakan stub no-op
agar engine `main-bot/src/worker.py` dan `main-vb/src/worker.py` tetap identik byte-for-byte
tanpa mengubah data outlet Bot O/C reguler.

Subteks status outlet pada kolom status tabel Virtual Brand (`admin_dashboard.html` / `getVbStatusSubtext`):
- Fase antrean buka (`PENDING_OPEN`): `"Bot sedang dalam proses pembukaan outlet"`.
- Fase antrean tutup (`PENDING_PAUSE`): `"Bot sedang dalam proses penutupan outlet"`.
- Fase pengambilan data/jadwal (`NOT_FETCHED_YET`, `FETCH_RETRYING`, `STATUS_UNKNOWN`): `"Bot sedang dalam proses pengambilan data outlet"`.

Header kolom jam operasional pada tabel Agency (`#adminTable`) dan tabel Virtual Brand (`.vb-store-table`)
wajib menggunakan teks `Jam Hari Ini`, serta label data kartu mobile Agency (`.admin-mobile-outlet-grid dt`)
dan label sel baris Virtual Brand (`.vb-store-field-label`) wajib menggunakan teks yang sama (`Jam Hari Ini`).

Subteks status outlet pada fungsi `getOutletPauseLine` di Dashboard Mitra (`user_dashboard.html`):
- Fase antrean tutup (`PENDING_PAUSE`): `"Bot sedang dalam proses penutupan outlet"` (tanpa informasi waktu buka kembali).
- Fase antrean buka (`PENDING_OPEN`): `"Bot sedang dalam proses pembukaan outlet"`.
- Fase tutup aktif (`PAUSE`): Menampilkan estimasi waktu buka kembali (`formatPauseResumeInline`).

Format judul dan isi riwayat aktivitas log audit pada Dashboard Mitra (`#historyLogs`)
dan drawer detail outlet Dashboard Admin (`#outletDetailHistoryLogs`) wajib mengikuti standar UX writing:
- Pelaku & aksi eksplisit: `"Outlet dibuka oleh Admin"`, `"Outlet dibuka oleh Merchant"`, `"Bot berhasil membuka outlet"`, `"Outlet ditutup oleh Admin"`, `"Outlet ditutup oleh Merchant"`, `"Bot berhasil menutup outlet"`.
- Setiap kartu log audit menampilkan: Judul aksi (baris 1), Nama outlet (baris 2), `Store ID <store_id>` (baris 3), dan Waktu format `DD MMM YYYY, HH:mm WIB` (baris 4, misal: `09 Sep 2026, 10:42 WIB`).

Nama pemilik akun pada kartu Ringkasan Akun Dashboard Mitra (`.mitra-account-summary #mitraName`)
ditampilkan secara langsung tanpa prefix `"Mitra "`, dan teks jumlah outlet pada dashboard mitra
wajib menggunakan kapitalisasi huruf besar `"Outlet"` (misal: `"4 Outlet"`).

Teks subtitle/caption pada halaman login mitra (`#loginSection .mitra-login-copy .card-subtitle`)
wajib tampil utuh dalam satu baris (`white-space: nowrap`) menggunakan ukuran font adaptif
(`clamp(12px, 3.4vw, 14px)`) dengan `max-width: 100%` tanpa batasan lebar buatan (340px / 304px),
agar tidak memotong frasa `"Bot Anda."` ke baris kedua baik pada mode desktop maupun mobile.

Drawer detail outlet (`.outlet-detail-panel`) pada dashboard admin menampilkan
informasi ringkas: identitas outlet, Jadwal reguler Shopee (tampilan langsung 7 hari
tanpa dropdown/akordion ataupun tombol minimize), dan kartu Aktivitas terbaru
(maksimal 10 log audit outlet) dengan scrollbar internal hanya pada container
daftar log (`.outlet-detail-history-list`). Seluruh panel drawer (`.outlet-detail-panel`)
dan pembungkus kontennya (`#outletDetailContent`) wajib menggunakan `overflow: hidden`
pada mode desktop, tablet, maupun mobile agar tidak memicu scroll global ataupun scroll
ganda pada drawer. Baris `Status live Shopee` ditiadakan dari drawer ini.

Badge status `Aktif` pada kartu Ringkasan Akun Mitra (`.mitra-account-summary #subBadge`)
wajib menggunakan warna latar belakang hijau (`#16a34a`) dengan teks putih untuk
merefleksikan status aktif secara positif.

Kolom `Link Mitra` pada tabel operasional admin (`#adminTable`) menampilkan
tautan langsung ke Dashboard Mitra (`.admin-table-mitra-link`) di sebelah kanan
kolom `Link` ShopeeFood tanpa logo Shopee, dan CTA buka dashboard mitra pada
panel drawer samping ditiadakan. Kolom Toggle (kolom 8) wajib tetap tampil utuh
pada semua breakpoint desktop dan laptop tanpa disembunyikan.

Card riwayat aktivitas mitra pada Dashboard Mitra (`.mitra-activity-card .history-list`)
wajib menggunakan internal scrollable container (`max-height: 380px`, `overflow-y: auto`)
tanpa pembatasan `.slice(0, 5)` pada client rendering agar tidak memicu scroll global
pada window/body.

Tab logs dan tab settings admin wajib menggunakan container internal masing-masing
(`.logs-page-shell`, `.settings-page-shell`) dengan `height: 100%` dan `overflow-y: auto`
pada mode desktop agar tidak memicu scroll global pada window/body serta menjaga agar
bagian atas kartu pengaturan tidak terpotong.

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

Service `bot-vb` mendukung file override `.env.vb` melalui direktif
`EnvironmentFile=-%PROJECT_DIR%/.env.vb` di bawah `.env` utama pada unit systemd,
agar variabel seperti `ALLOWED_USERNAMES=allvbadmin` tidak tertimpa oleh `.env` pusat.

Eksperimen `test_switch_xhr.py` wajib reach dashboard lebih dulu melalui
`src/core/browser.py`, lalu memverifikasi state UI dan struktur request partner
secara read-only dengan Vibium. Sebelum memanggil XHR `MerchantDetect`
manual, test wajib mencoba flow UI `browser.return_to_selector(driver)` untuk
meniru klik profile lalu `Pilih Merchant Lain` dan mengobservasi trigger
resource `PartnerMerchantDetectServer/MerchantDetect`. Artefak Vibium harus
disimpan di direktori temporary, bukan di dalam repo, dan tidak boleh
menyimpan token mentah di laporan teks yang dibagikan.

Setiap update kode, konfigurasi, atau perilaku aplikasi wajib:

1. Membuat atau memperbarui dokumentasi rilis di folder `/update`.
2. Mencatat aturan atau perubahan penting yang memengaruhi pekerjaan berikutnya di `AGENTS.md`.
3. Memilih nomor versi berdasarkan jenis perubahan, bukan sekadar menaikkan angka patch secara berurutan:
   - **MAJOR** (`1.x.x`): breaking changes, perubahan kontrak API, migrasi yang tidak kompatibel, atau perubahan arsitektur besar.
   - **MINOR** (`x.1.x`): fitur baru yang kompatibel dengan perilaku/API sebelumnya.
   - **PATCH** (`x.x.1`): bug fix, perbaikan kecil, optimasi handling error, atau patch stabilitas yang tidak mengubah kontrak.
4. Jika sebuah perubahan termasuk breaking atau feature, jangan menuliskannya sebagai patch hanya karena update sebelumnya memakai nomor patch. Nomor versi harus mencerminkan dampak perubahan.

File update wajib menggunakan format `update/<MAJOR>.<MINOR>.<PATCH>.md` dan mencantumkan seksi `Whats New`, `Spesifikasi`, dan `Handling`.

## Aturan UI Admin Mobile

Perubahan pada daftar outlet dashboard admin untuk breakpoint mobile wajib
menjaga parity informasi dengan mode desktop terbaru. Kartu mobile minimal
harus tetap menampilkan identitas outlet, jam operasional hari ini, action
terakhir, periode layanan, dan toggle outlet. Hindari meletakkan tombol
destruktif dominan di setiap kartu; aksi sensitif seperti hapus outlet harus
diletakkan di konteks detail outlet atau modal konfirmasi.

## Aturan Gaya Penulisan & Komunikasi (Copywriting & Dokumentasi)

1. **Penggunaan Emoji**:
   - Dilarang menggunakan emoji secara berlebihan (*excessive emojis*) pada teks respons, penjelasan, maupun dokumentasi rilis.
   - Gunakan gaya penulisan yang lugas, profesional, dan langsung pada inti teknis.

2. **Fakta Kode & Relevansi (Strict Project Relevance)**:
   - Dilarang mengarang fitur, membuat asumsi fiktif, atau menuliskan sesuatu yang tidak ada di dalam codebase project ini.
   - Seluruh penjelasan, analisis, dan dokumentasi rilis harus 100% akurat dan benar-benar terverifikasi (*strictly related*) dengan kode yang ada.
