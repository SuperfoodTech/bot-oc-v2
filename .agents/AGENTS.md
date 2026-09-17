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

Latest documented release: `1.21.0`.

Virtual Brand Dedicated Dashboard & Link Brand Integration:
- Setiap brand Virtual Brand memiliki dashboard publik mandiri via slug URL `/brand/{slug}` yang dapat diakses langsung oleh PIC brand tanpa memerlukan halaman login password.
- Brand Hero Card menampilkan nama brand, switch toggle 3-state tanpa label teks, 3 metrik status live (Live Buka, Perlu Cek, Live Tutup), dan tombol "Lihat Jadwal Operasional" yang membuka drawer bottom sheet jadwal 7 hari dari store ID pertama.
- Daftar outlet ditampilkan dalam format accordion collapsible (arrow down/up) dengan isi 2 kolom ringkas: Nama Outlet (listing/portal & Store ID) dan Status Live/Bot (tanpa link ShopeeFood di dashboard brand).
- Kolom ke-6 pada tabel outlet VB di Admin Dashboard (`admin_dashboard.html`) menampilkan "Link Brand" yang menghubungkan baris outlet ke dashboard brand masing-masing.

Penyederhanaan Visual 3-State Toggle & Eliminasi Label Teks:
- Seluruh switch toggle status (Agency, VB, Mitra) tampil bersih (*clean*) tanpa label teks pendamping saat dalam kondisi non-aktif/mati/terkunci.
- State di luar jadwal operasional (`state-closed`): toggle terkunci di posisi kiri, warna abu-abu (*gray*), berstatus `disabled`, tanpa label teks.
- State tutup/pause manual dalam jam operasional (`state-paused`): toggle di posisi kiri, warna merah (*red*), tanpa label teks.
- State buka/aktif dalam jam operasional (`state-open`): toggle di posisi kanan, warna hijau (*green*), tanpa label teks.

Virtual Brand Schedule-Aware Toggle Lock & UI Parity:
- Switch toggle Brand VB pada `admin_dashboard.html` menerapkan aturan pagar jadwal operasional yang identik dengan Dashboard Agency dan Mitra.
- Jika seluruh outlet di bawah brand berada di luar jadwal operasional (`bot_phase === 'WAITING_SCHEDULE'` atau `within_operating_schedule === false`), toggle switch terkunci ke posisi non-aktif (`state-closed`), berstatus `disabled`, menampilkan status pill `"Tutup Jadwal"`, dan memblokir klik toggle manual dengan pesan peringatan edukatif.

Dual-Speed Hybrid Scheduler & On-Demand Targeted Execution:
- Engine worker `sync_all_stores` pada `main-bot/src/worker.py` dan `main-vb/src/worker.py` mendukung parameter `target_store_ids` untuk mengeksekusi aksi buka/tutup toko secara spesifik (Express Lane < 5 detik) tanpa me-loop seluruh toko di dalam portal.
- Pemanggilan API `get_regular_hours` dan `get_special_hours` dilewati (*skip*) pada siklus patroli rutin jika data jadwal toko sudah tersimpan valid di database (`READY` / `FETCHED_EMPTY`), dan hanya dipanggil jika status jadwal masih `NOT_FETCHED_YET`, `FETCH_RETRYING`, atau dipicu `force_schedule_refresh=True`.
- `scheduler.py` memisahkan toko actionable (`actionable_store_ids`) dari pemeriksaan rutin heartbeat, dan daemon memprioritaskan dispatch portal yang memiliki toko actionable.
- Selesai eksekusi Express Lane di sebuah portal, bot memanfaatkan sesi aktif portal saat ini (*portal locality preference*) tanpa melakukan perpindahan merchant bolak-balik yang sia-sia (*zero ping-pong switch*).


Optimasi Memori & Pencegahan Out of Memory (OOM):
- Instance Chromium/Chrome pada `src/core/browser.py` dan `main-vb/src/core/browser.py` wajib menggunakan flag hemat memori: `--blink-settings=imagesEnabled=false`, limit V8 heap `--js-flags=--max-old-space-size=512`, cache disk/media `--disk-cache-size=52428800` & `--media-cache-size=52428800`, `--disable-features=Translate,OptimizationHints,MediaRouter`, `--renderer-process-limit=1`, dan `--disable-site-isolation-trials`.
- Network Interception CDP (`Network.setBlockedURLs`) memblokir font web (`*.woff`, `*.woff2`, `*.ttf`, `*.eot`) dan tracker pihak ketiga (*google-analytics*, *doubleclick*, *sensorsdata*, dll.) tanpa memblokir script JS, CSS, atau endpoint API Shopee.
- Setiap iterasi evaluasi loop utama daemon (`main-bot/src/daemon.py` dan `main-vb/src/daemon.py`) wajib menyertakan `gc.collect()` di dalam blok `finally:` untuk membebaskan cyclic reference memory leak secara deterministik.
- Penyesuaian konfigurasi browser dan pembersihan memori dilarang menginterupsi bot secara mendadak atau mematikan session 24/7 yang sedang aktif.

Frekuensi Polling Web & Efisiensi Database:
- Polling periodik cadangan pada Admin Dashboard (`ADMIN_OUTLET_SYNC_REFRESH_MS`), Dashboard Mitra (`USER_OUTLET_SYNC_REFRESH_MS`), dan Bot Monitoring menggunakan interval `60000ms` (60 detik) untuk menjaga efisiensi resource PostgreSQL dan CPU Web.
- Event listener `visibilitychange` aktif di dashboard Admin dan Mitra untuk melakukan sinkronisasi instan saat user memfokuskan kembali tab browser.
- Saluran Server-Sent Events (SSE) `/api/v1/admin/events` tetap menjadi saluran utama pengiriman perubahan state toko secara real-time (< 200ms).

Notifikasi Discord Virtual Brand (`send_discord_vb_group_summary`):
- Notifikasi Virtual Brand dikirimkan secara eksklusif ke `DISCORD_WEBHOOK_VB_URL` dalam format rekap summary per-VB Brand (bukan per-portal atau per-outlet individual) untuk 6 skenario utama (Full Open, Full Close, Partial Open, Partial Close, All Failed Open, All Failed Close).
- Seluruh pengiriman notifikasi individual/legacy ke Discord (`send_discord_error`, `send_discord_success`, `send_discord_skipped`, dan `DiscordWebhookHandler` di `logger.py`) dinonaktifkan secara total (No-Op untuk Discord).
- `bot-oc` (Agency reguler) dilarang keras menembak Discord Webhook dan hanya mengirim event notifikasi ke WhatsApp Gateway (`bot-wa`).
- Logika agregasi hasil aksi ditempatkan pada adapter `main-vb/src/db.py` (`record_log` / `_flush_pending_brand_notifications`) agar `main-vb/src/worker.py` tetap 100% identik byte-for-byte dengan `main-bot/src/worker.py`.
- Helper `_get_webhook_url()` mendukung dynamic reload dari `.env` / `.env.vb` tanpa memerlukan restart service bot patroli.

WhatsApp Gateway Microservice (`bot-wa`):
- Service `bot-wa` beroperasi secara penuh di luar container bot patroli (`fm-bot` & `fm-bot-vb`) tanpa menginterupsi alur kerja patroli Selenium atau memicu restart container bot yang sedang berjalan.
- Data riwayat aksi bot dibaca dari catatan database PostgreSQL (`audit_logs`) atau dikirim via webhook asinkron (`send_wa_webhook_async`) sehingga tidak mengganggu ketersediaan bot 24/7.

Filter Status Outlet Virtual Brand (`#vbMasterFilter` & `#mobileVbMasterFilter`):
- Filter `Status Master` digantikan secara penuh oleh filter operasional `Status Outlet`.
- Opsi filter mencakup: `Semua status` (`""`), `Perlu cek` (`PERLU_CEK`), `Live Buka` (`OPEN`), `Live Tutup` (`CLOSED`), dan `Tutup Sementara` (`PAUSE`).
- Opsi `Perlu cek` menyaring outlet yang membutuhkan penanganan (patroli gagal, error, atau status abnormal).

Toolbar filter Virtual Brand (`.vb-filter-grid`):
- Field input Store ID (`#vbStoreIdFilter`) dan tombol Reset Filter (`.vb-reset-button`) wajib memiliki tinggi seragam `36px` dengan padding, border, radius (`8px`), dan font `Nunito` yang konsisten dengan custom select filter lainnya.
- Tombol reset filter menggunakan label `"Reset filter"` dan class `btn-compact`.

Interaksi kartu grup Virtual Brand (`.vb-brand-card-head`):
- Tombol chevron expand terpisah (`.vb-expand-button`) ditiadakan.
- **Single click** pada baris/header kartu grup melakukan expand/collapse detail Store ID hanya untuk grup yang diklik.
- **Double click** pada baris/header kartu grup melakukan expand all jika ada grup yang tertutup, atau collapse all jika seluruh grup sedang terbuka.
- Kontrol switch toggle ON/OFF grup (`.vb-brand-toggle`) wajib diberi `event.stopPropagation()` agar pengubahan status grup tidak memicu expand/collapse kartu.

Kolom ke-8 pada tabel operasional admin (`#adminTable`) diberi label header `Status`
(menggantikan label `Toggle`).

Tabel Virtual Brand (`.vb-store-table`) memiliki kolom ke-7 `Link OFD` di sebelah kanan
kolom `Jadwal Khusus` yang menampilkan tautan langsung ke ShopeeFood (`.admin-table-shopeefood-link`)
menggunakan icon dan teks `Lihat di ShopeeFood` dengan `event.stopPropagation()` agar klik tidak
memicu drawer jadwal VB.

Font design dan tipografi baris tabel Virtual Brand (`.vb-store-table`), khususnya baris
`Jam Hari Ini` (`.vb-store-hours .today-operating-hours`) dan seluruh teks tabel VB,
disamakan secara penuh dengan tabel Agency (`#adminTable`) menggunakan font `Nunito`
dengan warna teks, ukuran font, dan font-weight yang konsisten.

Sinkronisasi Jadwal Khusus (*Special Hours*) dari endpoint `/api/seller/store/special-hours`
disimpan ke kolom `outlet_states.shopee_special_hours` (`jsonb`) saat bot mengakses tab Business Hours.
Validasi identitas toko (`StoreIdentityMismatch`) wajib diterapkan secara ketat sebelum menyimpan jadwal.
Tampilan Jadwal Khusus di Dashboard Admin:
- Tab Agency: Tampil di dalam Drawer Detail Outlet pada kartu "Jadwal khusus Shopee".
- Tab Virtual Brand: Tampil sebagai kolom ke-6 "Jadwal Khusus" di sebelah kanan kolom "Jam Hari Ini" pada tabel `.vb-store-table` dan di dalam Drawer Jadwal VB.

Parsing Google Sheet CSV pada endpoint sinkronisasi Agency (`/api/v1/admin/sync-source`)
menggunakan deteksi nama header secara dinamis (`find_col`) pada `src/core/sheets.py`
dan `main-vb/src/core/sheets.py` agar impor data tetap berjalan lancar saat ada penambahan
atau pergeseran kolom spreadsheet (seperti penambahan kolom `WA Pemilik`).

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
