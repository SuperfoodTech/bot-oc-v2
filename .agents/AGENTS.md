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

Latest documented release: `1.34.0`.

Mismatch-Driven Instant Schedule Verification & Special Hours Precedence:
- Mengintegrasikan mekanisme On-Demand Schedule Verification pada `main-bot/src/worker.py` dan `main-vb/src/worker.py`: ketika status live outlet di Shopee terdeteksi `OPEN` namun evaluasi awal bot bernilai `ACTION_CLOSE` (akibat sisa jeda pause lama atau di luar jadwal reguler), bot secara instan melakukan verifikasi tarik ulang data `/special-hours` (serta regular hours jika kosong) dari Shopee ke database sebelum mengeksekusi penutupan paksa.
- Memprioritaskan evaluasi Jadwal Khusus (*Active Special Hours*) di atas penanganan pause sementara (*Active Pause Until*) pada `src/core/decision.py` dan `main-vb/src/core/decision.py`, menjamin toko yang beroperasi di bawah Jadwal Khusus Buka Shopee 100% dihormati dengan keputusan `NO_CHANGE` tanpa intervensi penutupan paksa bot.
- Menerapkan auto-cleanup pembersihan parameter `pause_until` lama secara atomik di database ketika jadwal aktif Shopee terkonfirmasi, mencegah sisa pause usang mengunci operasional toko pada putaran patroli berikutnya.
- Menjaga modul `main-vb/src/worker.py` dan `main-bot/src/worker.py` serta `src/core/decision.py` dan `main-vb/src/core/decision.py` 100% identik byte-for-byte.

Virtual Brand Toggle SQL Type Casting & Import Integrity:
- Memperbaiki `psycopg.errors.DatatypeMismatch` pada query `request_status` dan `request_brand_status_public` di `src/backend/vb.py` dengan menambahkan cast eksplisit `::timestamptz` pada ekspresi `CASE WHEN %s='PAUSED' THEN %s::timestamptz ELSE NULL END` untuk kolom `pause_from` dan `pause_until`.
- Memperbaiki `NameError` pada `src/backend/vb.py` dengan mengimpor `datetime` dan `ZoneInfo` secara eksplisit.
- Menambahkan import `logging` pada `src/backend/main.py` untuk penanganan exception sinkronisasi daftar owner WhatsApp.

Unified Scheduled Future Pause Engine & 1:1 Dual Interactive Start-Until Pickers:
- Menghadirkan fitur Penjadwalan Tutup Masa Depan (*Scheduled Future Pause*) yang memungkinkan Merchant maupun Admin untuk mengatur waktu mulai tutup (*Start Date-Time*) dan target buka kembali (*Until Date-Time*) ke masa depan secara fleksibel tanpa mengunci waktu mulai hanya pada saat ini.
- Menerapkan arsitektur 1:1 identik dan konsisten di seluruh 4 antarmuka picker:
  1. Dashboard Mitra Agency (`src/backend/templates/user_dashboard.html`)
  2. Admin Console Agency Modal (`src/backend/templates/admin_dashboard.html`)
  3. Admin Console Virtual Brand Modal (`src/backend/templates/admin_dashboard.html`)
  4. Dashboard Mitra Virtual Brand (`src/backend/templates/brand_dashboard.html`)
- Menerapkan Dynamic Past Time Restriction & Auto-Adjustment:
  - Tanggal/Waktu Mulai: Opsi jam/menit lampau otomatis di-disable saat memilih hari ini (`Start >= Now - 1min`), dan seluruh 24 jam / 60 menit aktif bebas saat memilih tanggal masa depan.
  - Tanggal/Waktu Berakhir: Opsi jam/menit sebelum atau sama dengan waktu mulai otomatis di-disable (`Until > Start`). Jika pengguna menggeser waktu mulai melewati waktu berakhir, waktu berakhir secara reaktif otomatis bergeser maju (`Start + 2 jam`).
- Engine Eksekusi Otonom & Boundary Express Lane:
  - Penambahan kolom `pause_from` pada tabel `outlet_states` dan `pause_from`, `requested_pause_from` pada tabel `vb_brands` via migrasi `016_scheduled_pause_from.sql`.
  - Outlet/Brand dengan jadwal tutup masa depan (`pause_from > now`) tetap beroperasi dan buka secara normal (`effective_status = 'ON'`) dengan status banner transparan: `'Terjadwal tutup: [Tgl/Bln] [Jam] - [Jam] WIB'`.
  - Ketika waktu mencapai `now >= pause_from`, bot secara otomatis mengeksekusi penutupan outlet (`TARGET_CLOSE`), dan membuka kembali secara otomatis saat `now >= pause_until`.
  - Scheduler (`main-bot/src/scheduler.py` dan `main-vb/src/scheduler.py`) mengenali boundary `pause_from` sebagai `P1_BOUNDARY` actionable yang langsung dialihkan ke Express Lane demi presisi waktu penutupan instan.

Unified 1:1 Dynamic Past Time Restriction & Strict Duration Picker Guard:
- Menerapkan pembatasan pemilihan waktu lampau (*Past Time Restriction*) secara dinamis dan 1:1 konsisten di seluruh 4 antarmuka modal/custom date-time picker:
  1. Dashboard Mitra Agency (`src/backend/templates/user_dashboard.html`)
  2. Admin Console Agency Modal (`src/backend/templates/admin_dashboard.html`)
  3. Admin Console Virtual Brand Modal (`src/backend/templates/admin_dashboard.html`)
  4. Dashboard Mitra Virtual Brand (`src/backend/templates/brand_dashboard.html`)
- Saat user memilih tanggal hari ini (*Today*):
  - Seluruh opsi jam sebelum jam saat ini (`hour < currentHour`) secara otomatis di-disable (`option.disabled = true`).
  - Ketika jam saat ini dipilih (`hour === currentHour`), seluruh opsi menit yang sudah lewat atau sama dengan menit saat ini (`minute <= currentMinute`) secara otomatis di-disable (`option.disabled = true`), dan nilai menit otomatis bergeser ke menit valid pertama (atau naik ke jam berikutnya jika menit adalah 59).
  - Saat jam diubah oleh pengguna, listener `change` pada jam secara reaktif memperbarui opsi menit (`disabled` untuk menit lampau hanya pada jam saat ini).
- Saat user memilih tanggal masa depan (*Future Date*), seluruh opsi 24 jam (00..23) dan 60 menit (00..59) otomatis aktif (*enabled*) secara deterministik.
- Menjaga fungsi validasi guard `target > now` saat tombol *Terapkan* / *Pilih* ditekan, mencegah payload durasi lampau terkirim ke backend.

Shopee Special Hours Open Recognition, Contract Compliant Toggle Lockdown & Empty Schedule UX Writing Normalization:
- Mengintegrasikan penanganan evaluasi Jadwal Khusus Buka (*Special Hours Open*) pada `evaluate_outlet_status` di `src/core/decision.py` & `main-vb/src/core/decision.py`, menghasilkan keputusan deterministik `NO_CHANGE` (`Mengikuti Jadwal Khusus Shopee`) tanpa melempar error ketiadaan jadwal reguler saat toko beroperasi berdasarkan jadwal khusus.
- Menerapkan penguncian switch toggle (*Strict Toggle Lockdown / disabled off* di sisi kiri `state-closed`) pada Dashboard Mitra (`user_dashboard.html`) dan Admin Console (`admin_dashboard.html` & `db.py`) saat terdapat Jadwal Khusus aktif (baik Buka maupun Tutup), memastikan bot 100% menghormati jadwal khusus Shopee tanpa intervensi.
- Menstandarkan pesan tunggal Hero Card & Tooltip toggle menjadi `'Bot tidak berfungsi karena terdapat Jadwal Khusus!'`.
- Menampilkan rincian jam operasional Jadwal Khusus Buka (`HH:mm - HH:mm WIB`) pada drawer jadwal ("Tampilkan jadwal") dan ringkasan jadwal hari ini di antarmuka mitra.
- Mengeliminasi seluruh cabang teks keliru `'Ada kesalahan data, harap hubungi Admin'` dan `'Jadwal operasional belum tersedia'`, menggantikannya secara faktual menjadi `'Tidak memiliki jadwal operasional'` untuk outlet yang memang tidak mengatur jadwal di Shopee (`FETCHED_EMPTY`), serta `'Sedang sinkronisasi jadwal'` saat jadwal dalam antrean penarikan.

Mitra Dashboard Special Hours Closed UX Writing Normalization:
- Mengganti teks meta status dan jadwal operasional pada outlet yang tutup akibat jadwal khusus (*Special Hours*) di Dashboard Mitra (`/mitra/{slug}` di `src/backend/templates/user_dashboard.html`).
- Pada kondisi tutup karena jadwal khusus (*Full Day Close* / di luar rentang jam khusus hari ini), teks kombinasi jadwal biasa (`Akan buka kembali [Hari], [Jam] WIB` dan `Jadwal hari ini: [Hari] [Jam]`) digantikan secara bersih dengan satu baris pesan tegas: `'Bot tidak berfungsi karena terdapat Jadwal Khusus!'`.
- Menyelaraskan tooltip dan notifikasi toast saat toggle switch diklik saat periode jadwal khusus menjadi `'Bot tidak berfungsi karena terdapat Jadwal Khusus!'`.
- Mengintegrasikan pengecekan `getActiveSpecialHoursEntry` dan `isWithinSpecialHoursIntervals` pada kalkulasi `getOutletStateContext` frontend serta `is_within_special_hours_intervals` pada `_is_within_shopee_schedule` & `_get_schedule_gate_detail` di `src/backend/main.py` dan `src/backend/db.py`.
- Menampilkan rincian Jadwal Khusus Shopee pada panel drawer jadwal saat mitra menekan tombol "Tampilkan jadwal".

Virtual Brand 3-State Group Status Filter (ON, PAUSE, CLOSED):
- Menambahkan opsi filter Status Grup Virtual Brand (VB) menjadi 3 state operasional lengkap: `ON`, `PAUSE`, dan `CLOSED` (baru) pada Desktop dropdown (`#vbStatusFilter`) dan Mobile Filter Sheet (`#mobileVbStatusFilter`) di `src/backend/templates/admin_tab_vb.html`.
- Mengintegrasikan kalkulasi state toggle deterministik (`brand.vbToggleState` & `brand.isScheduleLocked`) langsung pada `buildVbBrandViews()` di `src/backend/templates/admin_dashboard.html`:
  - `ON`: Brand aktif buka dan mengikuti jam operasional normal (toggle hijau di kanan / `state-open`).
  - `PAUSE`: Brand dalam kondisi tutup sementara / pause manual pada jam operasional (toggle kuning di tengah / `state-paused`).
  - `CLOSED`: Brand yang tutup karena di luar jam operasional (seluruh outlet berada di luar jadwal Shopee / `WAITING_SCHEDULE` / `within_operating_schedule === false` dengan visual switch toggle terkunci abu-abu disable di sebelah kiri / `state-closed` / `is-schedule-disabled`).
- Memperbarui fungsi `getFilteredVbBrandViews()` untuk menyaring grup brand sesuai state toggle operasional, serta menyinkronkan pembaruan ringkasan data (`#vbResultsSummary`) dan kalkulasi kartu statistik ringkasan VB (`#vbStatsGrid`).
- Menjaga kompatibilitas mundur (*backward compatibility*) untuk nilai legacy `OFF` yang dipetakan aman ke status `PAUSE`.

Mitra Dashboard Action Role Attribution Consistency:
- Menghapus pembacaan cookie sesi Admin pada endpoint `POST /api/v1/user/pause` di `src/backend/main.py`.
- Memastikan seluruh tindakan penutupan sementara (pause) maupun pembukaan kembali yang dieksekusi melalui antarmuka Dashboard Mitra Agency (`/mitra/{slug}`) secara konsisten dan deterministik dicatat sebagai aksi **Merchant / Mitra** (`USER_PAUSE_STORE` / `USER_RESUME_STORE`).
- Mencegah kontaminasi label `Admin` pada riwayat aktivitas mitra saat admin membuka atau menguji link dashboard mitra menggunakan browser yang sama dengan sesi admin yang sedang aktif.
- Tindakan toggle yang dilakukan langsung melalui Admin Console (`/api/v1/admin/outlets/toggle`) tetap dipertahankan tercatat sebagai `ADMIN_PAUSE_STORE` / `ADMIN_RESUME_STORE`.

Agency Google Sheet Sync Automatic Deletion Reconciliation:
- Mengintegrasikan mekanisme rekonsiliasi otomatis pada fungsi "Fetch dari Sheet" (`run_import_sheet` di `src/core/import_sheet.py` dan `deactivate_missing_agency_stores` di `src/backend/db.py`).
- Saat baris outlet dihapus secara permanen dari Google Sheet sumber, outlet Agency aktif terkait di PostgreSQL yang tidak lagi ditemukan di dalam sheet secara otomatis dinonaktifkan (`is_active = false`).
- Outlet yang dihapus dari sheet seketika hilang dari Dashboard Admin & Mitra Agency serta langsung dilepaskan dari antrean patroli bot tanpa merusak integritas relasional data histori (`automation_logs`, analitik guarding, dan audit trail).
- Menambahkan counter `removed_from_sheet` pada respons REST API `/api/v1/admin/sync-source` serta notifikasi Toast interaktif di Admin Dashboard (`Fetch selesai: X aktif, Y nonaktif, Z dihapus dari sheet, W dilewati`).

Mobile Bottom Navbar 5-Button Alignment & Bot WA Streamlining:
- Menyembunyikan menu **Bot WA** (`#tabBtnWA`) dan **Logs** (`#tabBtnLogs`) pada mode mobile (`@media (max-width: 767.98px)`) di `styles.css`.
- Menempatkan menu **Analisis** (`#tabBtnAnalytics`) di bottom navbar mobile, sehingga tersusun tepat **5 tombol** dalam 1 baris yang rapi dan simetris tanpa wrapping/overflow:
  1. `Agency` (kiri)
  2. `Virtual Brand` (tengah-kiri)
  3. `Fetch` (tombol floating bulat di tengah)
  4. `Analisis` (tengah-kanan)
  5. `Settings` (kanan)
- Pada mode desktop, urutan menu di sidebar tetap lengkap 6 menu: `Agency`, `Virtual Brand`, `Analisis`, `Logs`, `Bot WA`, dan `Settings`.

Interactive Entity Guarding Deep-Dive Detail Drawer & Operational Diagnostics:
- Mengintegrasikan interaktivitas Slide-over Sheet / Drawer pada tabel **"Peringkat Brand / Outlet Terintervensi"** di Tab Analisis (`admin_tab_analytics.html`).
- Saat baris brand (misal *Katsunami*) atau outlet agency diklik, panel drawer kanan terbuka secara mulus (*slide-over*) menampilkan data mendalam:
  1. Ringkasan Guarding (Total Intervensi, Guarding Auto-Open, Proteksi Pause, Tingkat Keberhasilan, dan Waktu Intervensi Terakhir).
  2. Distribusi Waktu Kritis & Jam Paling Sering Diintervensi (Puncak Auto-Open `HH:mm WIB`, Puncak Proteksi Pause `HH:mm WIB`, dan 3 jam tersibuk).
  3. Komposisi Guarding Otonom (Progress visual bar perbandingan Auto-Open vs Proteksi Pause).
  4. Breakdown Cabang Terintervensi (Tabel mini cabang/outlet di bawah brand dengan rincian total, buka, tutup, dan success rate).
  5. Riwayat Intervensi Terakhir (Log stream 6 intervensi terbaru lengkap dengan badge aksi, timestamp WIB, nama cabang, dan alasan/keterangan).
- Endpoint REST API baru `@app.get("/api/v1/analytics/entity-detail")` di `src/backend/main.py` dan fungsi analitik mendalam `get_entity_analytics_detail` di `src/backend/db.py`.
- Dilengkapi interaksi modern: backdrop blur, tombol close, pintasan keyboard `ESC`, transition animation responsif, dan full dark mode support.

Dedicated Autonomous Guarding Analytics Engine & Operational Analysis Tab:
- Mengintegrasikan tab baru **"Analisis"** sebagai menu ke-3 persis di bawah Virtual Brand pada Admin Console (`admin_dashboard.html`), lengkap dengan sinkronisasi URL state (`?tab=analytics`), responsive layout, dan perbaikan scroll container (`overflow-y: auto`).
- Mengimplementasikan filter query PostgreSQL murni aksi Guarding otonom di `src/backend/db.py` (`get_analytics_data`), mengecualikan seluruh intervensi manual/user trigger (`USER_PAUSE`, `ADMIN_PAUSE`, toggle OFF).
- Menyajikan metrik operasional terperinci: Total Intervensi Guarding, Guarding Auto-Open, Proteksi Masa Pause, Tingkat Keberhasilan, Distribusi Waktu 24 Jam WIB (Open vs Close), Panel Mekanisme Kerja Guarding (Auto-Open & Proteksi Pause), Tren Volume Harian, Pola Sesi Operasional (Pagi, Siang Peak, Sore, Malam, Dini Hari), dan Peringkat Brand/Outlet Terintervensi (dengan filter terfokus pada rentang data rilis valid: Hari Ini & 7 Hari).
- Memastikan UI bebas dari emoji (hanya SVG/CSS badge murni) dan teks analisis faktual tanpa hiperbola.

Preemptive Cooperative On-Demand Execution Engine & Instant Sleep Interruption:
- Mengintegrasikan pemeriksaan `has_pending_brand_actions()` di setiap iterasi awal pemeriksaan outlet pada `sync_all_stores()` di `main-vb/src/worker.py` dan `main-bot/src/worker.py`.
- Ketika user mengubah status brand di dashboard saat bot sedang menjalankan patroli rutin (*PATROL LANE*) pada portal besar (30–50 outlet), loop patroli rutin **langsung berhenti (*break / yield*) dalam waktu $< 1$ detik**.
- Mengembalikan kontrol ke `daemon.py` seketika untuk mempromosikan aksi toggle tersebut ke **Priority 100 (P0 Express Lane)**, memangkas latensi eksekusi dari 3–5 menit menjadi **$< 3\text{--}5$ detik**.
- Menambahkan deteksi `has_pending_brand_actions()` di dalam perulangan 1-detik *idle sleep* pada `main-vb/src/daemon.py` dan `main-bot/src/daemon.py`, menjamin bot langsung bangun seketika saat ada aksi on-demand tanpa menunggu timer tidur berakhir.
- Menjaga modul `main-vb/src/worker.py` dan `main-bot/src/worker.py` 100% identik *byte-for-byte*.

Virtual Brand Activity Card Streamlining:
- Menghapus tampilan nama outlet dan Store ID pada baris riwayat kartu aktivitas (*activity card / log card*) di Dashboard Mitra Virtual Brand (`/brand/{slug}`), sehingga log aktivitas tampil lebih bersih, ringkas, dan fokus pada aksi/status brand.

Virtual Brand Dashboard Card Spacing & Activity Log Card Alignment:
- Menambahkan layout container flex column (`gap: 14px`) pada `.brand-dashboard-content` serta menormalkan margin pada `.brand-activity-card` di Dashboard Mitra Virtual Brand (`/brand/{slug}`).
- Memastikan jarak vertikal antara kartu brand (hero card) dan kartu riwayat aktivitas (activity / log card) konsisten dan presisi sebesar 14px, seragam dengan jarak antar-kartu brand saat seorang owner memiliki lebih dari satu brand.

iOS Safari & Mobile WebKit Custom Date & Time Picker Interaction Fix:
- Memperbaiki arsitektur DOM modal custom duration ("Durasi lain") pada seluruh dashboard (Mitra Agency `user_dashboard.html`, Admin Agency & VB `admin_dashboard.html`, dan Mitra Virtual Brand `brand_dashboard.html`) dengan melepaskan pembungkus `<label>` di sekeliling `.custom-picker-anchor`, mencegah synthetic click activation pada Safari iOS yang memicu reset otomatis ke tanggal awal saat user menekan angka kalender.
- Mencegah event bubbling dan default behavior (`e.preventDefault()`, `e.stopPropagation()`) pada pemilihan tanggal hari (`selectPickerDay`), tombol navigasi bulan (`shiftPickerMonth`), dan tombol aksi modal (`apply` / `close`).
- Memperbaiki parsing datetime ISO (`parseCustomUntil`, `parseAdminCustomUntil`, `parseVbCustomUntil`, `parseBrandCustomUntil`) menggunakan regex parsing komponen tanggal lokal aman untuk mencegah bug *invalid date* / *UTC timezone drift* pada WebKit / iOS Safari.
- Memperbaiki fungsi seleksi tanggal VB (`selectVbPickerDay` dan `selectBrandPickerDay`) agar membuat objek `Date` baru lengkap (tahun, bulan, tanggal) tanpa tertahan pada bulan sebelumnya saat berpindah bulan.

Virtual Brand Admin Dashboard & Mitra Quick Copy UI Refinement:
- Memperbarui tombol Link Dashboard Virtual Brand pada Admin Dashboard dengan background merah (`#be1a1a`), hover state dinamis, dan dark mode contrast yang optimal.
- Menambahkan tombol instan `[Copy]` link dashboard brand di sisi kiri tombol Link Dashboard Virtual Brand lengkap dengan visual feedback animasi checkmark.
- Menambahkan tombol copy link mitra instan pada tabel agency (`.admin-table-mitra-cell` dan `.admin-mobile-mitra-group`).
- Memperbaiki layout responsif mobile Virtual Brand dengan menempatkan tombol panah expand/collapse chevron di sisi paling kanan.
- Menyelaraskan teks dan perataan UX loading state brand (`"Memuat data brand..."`) menjadi full-width horizontal center di `#vbStatsGrid`.
- Menyelaraskan field filter card Virtual Brand (Desktop & Mobile Sheet) kembali ke layout resmi standar tim (Grup, Status Grup, Portal, Status Outlet, Store ID) dengan integrasi custom searchable dropdown styling.

Native WhatsApp Gateway Integration, Two-Tier Anti-Spam / Anti-Ban Deduplication & Unified Dashboard UI:
- Mengintegrasikan tab WhatsApp Gateway (`admin_tab_wa.html`) secara langsung ke dalam Single Page Application (SPA) dashboard admin port utama tanpa pembungkus `<iframe>` eksternal.
- Menyediakan UI pemantauan real-time: status koneksi, scan QR canvas interaktif, metrik antrean/pesan terkirim, tombol sinkronisasi sheet Google Drive (`Fetch dari Sheet`), daftar owner & outlet terhubung, serta modal konfirmasi putus sesi kustom yang bersih dan elegan.
- Menerapkan *Two-Tier Anti-Spam & Anti-Ban Deduplication Architecture*:
  - Lapis 1 (Backend Web & Bot Core di `src/core/notifier.py`): In-memory TTL cache 5 menit untuk mencegah duplicate webhook dispatch.
  - Lapis 2 (Gateway Engine di `bot-wa/src/index.js`): In-memory TTL cache 5 menit (`_sentHistory` dedup key), deduplikasi antrean aktif, batas antrean aman (`MAX_QUEUE_SIZE`), humanized typing simulation (`composing`), dan jeda pengiriman dinamis 2.5s - 4.5s.
- Menyelaraskan 1:1 format template pesan WhatsApp Agency dengan Discord Webhook resmi, dilengkapi hyperlink ShopeeFood per-outlet dan footer CS FoodMaster.
- Menyediakan automated systemd service installer (`systemd/setup.sh` & `systemd/bot-wa.service`) untuk menjamin operasional gateway berjalan independen dan auto-restart.

Deterministic Python Runtime Memory Reclamation & Proactive Browser Recycling:
- Mengintegrasikan pemanggilan C `libc.so.6` `malloc_trim(0)` di dalam blok `finally:` pada loop evaluasi utama `main-bot/src/daemon.py` dan `main-vb/src/daemon.py` setelah `gc.collect()`, mengembalikan *unmapped memory pages* dan *arena fragmentation* Python langsung ke Kernel Linux OS secara deterministik di setiap akhir siklus patroli.
- Mengintegrasikan Proactive Browser Recycling (`recycle_browser_sessions`) setiap 100 siklus patroli (`BROWSER_RECYCLE_INTERVAL_CYCLES`) yang hanya dieksekusi pada *safe idle window* (Zero Demand, Zero Pending Retry, dan jeda tidur aman $\ge 30\text{--}60$ detik).
- Menerapkan *Instant Re-warmup* saat idle sehingga browser baru langsung siap tempur di latar belakang (Zero Cold-Start & Zero OTP) dan mereset penggunaan RAM Chrome kembali ke $\sim 80\text{ MB}$.
- Menambahkan flag Chromium `--disable-features=BackForwardCache` pada `src/core/browser.py` untuk mematikan penimbunan riwayat snapshot DOM di memori browser.

Instant Boundary & Schedule Express Lane Dispatch (<3s Zero Order Leak):
- Mengubah flag `actionable` pada event boundary waktu kritis di `main-bot/src/scheduler.py` dan `main-vb/src/scheduler.py` (`P1_BOUNDARY`, `P1_PAUSE_EXPIRY`, dan `P2_NEXT_SCHEDULE`) dari `False` menjadi `True` (saat memenuhi syarat eligibilitas Auto Open).
- Menambahkan parameter `grace_seconds` (120 detik) pada `get_next_schedule_start` (`src/core/decision.py` dan `main-vb/src/core/decision.py`), memastikan saat jam boundary tiba (misal pergantian sesi jam 10:00:00 WIB), outlet target seketika dikenali sebagai `actionable` dan langsung masuk ke jalur `⚡ [EXPRESS LANE]`.
- Mengeliminasi jeda antrean portal sweep 40–60 detik sehingga penutupan ulang toko yang sedang pause maupun pembukaan toko saat jam buka reguler dieksekusi secara instan (< 1-3 detik) tanpa risiko kebobolan order masuk.

Dedicated Transient Action Failure Priority Retry Queue & Auto-Schedule Refresh on Mismatch:
- Mengintegrasikan antrean prioritas pemulihan cepat (*Priority Retry Queue* via `FAILED_RETRY_TRACKER`) pada `main-bot/src/daemon.py` dan `main-vb/src/daemon.py` untuk mengeksekusi ulang outlet yang mengalami kegagalan sesaat (*transient failure* / *dropdown timeout* / *delay network*) dalam jeda 15s -> 45s -> 90s melalui jalur cepat `[RETRY EXPRESS LANE]` tanpa harus menunggu putaran keliling penuh (*floor sweep*).
- Menyediakan batas pengaman *exponential backoff & cooldown* 15 menit jika outlet gagal lebih dari 3 kali berturut-turut untuk mencegah *resource starvation*.
- Mengintegrasikan deteksi otomatis jadwal kedaluwarsa (*TTL 24 jam / Daily Schedule Staleness Check*) pada `worker.py` (`_is_schedule_stale`) untuk menjamin jadwal khusus (*Special Hours*) Shopee harian otomatis ter-update.
- Menambahkan auto-trigger reset jadwal (`_mark_schedule_fetch_retry`) saat terjadi `VERIFICATION_MISMATCH` pasca-eksekusi, memastikan jika toko gagal dibuka akibat jadwal khusus baru yang belum ter-fetch, bot akan langsung menarik ulang jadwal khusus dan reguler pada kunjungan berikutnya.

Virtual Brand Dedicated Dashboard Toggle Resume & Clean Open Schedule State:
- Memperbaiki transisi toggle status dari OFF/PAUSED kembali ke ON pada Dashboard Brand (`/brand/{slug}` & `src/backend/vb.py`): memastikan `pause_until` dan `requested_pause_until` direset menjadi `NULL` secara atomik saat status brand diminta `ON`, sehingga tidak lagi terjebak pada state pause lama.
- Menghapus label teks `'Sedang buka'` saat outlet brand sudah aktif buka (`openedCount >= 1`), sehingga Hero Card hanya menyajikan baris jadwal operasional hari ini (`Jadwal hari ini: HH:mm - HH:mm WIB`) yang bersih dan rapi.

Virtual Brand Live State Normalization & Status Count Determinism:
- Memperbaiki penentuan agregasi status live outlet Virtual Brand pada `get_brand_by_slug_or_id` (`src/backend/vb.py`) dan frontend `brand_dashboard.html`.
- Menggunakan `store.get("live_state")` yang sudah dinormalisasi oleh `derive_outlet_runtime_state` (mengenali nilai mentah Shopee API seperti `"ON"` / `"OFF"` / `"PAUSE"` menjadi `"OPEN"` / `"CLOSED"` / `"PAUSE"`), mengeliminasi false positive status `failure_count` / "Perlu Cek" dan label antrean pembukaan semu pada brand yang seluruh outletnya sudah aktif buka.

Virtual Brand Dedicated Dashboard Clean Meta & Dynamic Transition Status:
- Mengembalikan Hero Card Dashboard Publik Virtual Brand (`/brand/{slug}`) ke tampilan bersih (*clean*) dan minimalis tanpa kartu metrik ("Live Buka", "Perlu Cek", "Live Tutup") dan tanpa accordion detail outlet.
- Mengintegrasikan baris meta status & jam hari ini (`.mitra-outlet-meta` & `.mitra-outlet-meta-row`) dengan ikon jam yang 1:1 identik dengan Dashboard Mitra Agency (terletak di atas tombol aksi "Lihat Jadwal").
- Logika label status dinamis:
  - **Transisi ON -> OFF (Penutupan)**: Selama masih ada outlet yang belum tutup atau gagal tutup, menampilkan label `'Bot sedang dalam proses penutupan outlet'`. Saat seluruh outlet telah tertutup, menampilkan estimasi waktu buka kembali (`Akan buka kembali pada HH:mm WIB` / pause-resume) atau `'Akan dibuka kembali saat otomatisasi diaktifkan.'`.
  - **Transisi OFF -> ON (Pembukaan)**: Jika minimal sudah ada satu outlet yang berhasil dibuka oleh bot (`openedCount >= 1`), label otomatis berubah menjadi `'Sedang buka'`. Jika belum ada outlet yang berhasil dibuka (masih antrean), menampilkan `'Bot sedang dalam proses pembukaan outlet'`.
  - **Di Luar Jam Operasional**: Menampilkan `'Di luar jam operasional'` dan jadwal hari ini.

Agency Outlet Action Discord Webhook Notifications:
- Mengintegrasikan notifikasi Discord Webhook khusus Agency (`DISCORD_WEBHOOK_AGENCY_URL` / `DISCORD_WEBHOOK_URL`) saat bot patroli berhasil membuka (`🟢 OUTLET BERHASIL DIBUKA BOT`) atau menutup (`🔴 OUTLET BERHASIL DITUTUP BOT`) outlet Agency.
- Format pesan menyajikan Nama Outlet, Store ID, hyperlink ShopeeFood (`[Link ShopeeFood](https://shopee.co.id/universal-link/now-food/shop/<store_id>)`), dan footer resmi FoodMaster Bot Team (WA CS: `wa.me/6285183151531`).
- Notifikasi Agency disajikan bersih tanpa label atau embel-embel "GUARDING" baik pada pemicu patroli otomatis maupun manual.
- Mendukung deduplikasi pesan atomik (cache TTL 5 menit) dan pengiriman asinkron via `send_discord_agency_action_notification` di `src/core/notifier.py` yang dipanggil melalui `db.record_log` (`src/backend/db.py`) serta `send_discord_success`.

Virtual Brand Dedicated Dashboard Outlet Status Aggregation & Breakdown:
- Mengintegrasikan baris 3 kartu metrik ringkasan status live (`.brand-metrics-row`) pada Hero Card Dashboard Mitra VB (`/brand/{slug}`): `Live Buka` (`.is-opened`), `Perlu Cek` (`.is-failure`), dan `Live Tutup` (`.is-closed`).
- Menambahkan tombol aksi `Daftar Outlet (N)` berdampingan dengan `Lihat Jadwal` pada `.brand-hero-actions`.
- Menambahkan komponen kartu accordion collapsible `Daftar Outlet` (`.brand-outlets-card`) yang menyajikan breakdown macam-macam outlet di bawah brand (menampilkan nama portal/merchant, nama listing, Store ID, badge status live interaktif, serta subteks jam hari ini / antrean bot).

Virtual Brand Dedicated Dashboard 1:1 Pause Modal & Custom Picker:
- Modal konfirmasi penutupan sementara di Dashboard Publik Virtual Brand (`/brand/{slug}`) dibuat **1:1 identik** dengan Admin VB Modal dan Dashboard Mitra (mencakup step indicator, judul dinamis `Tutup <Nama Brand>`, box preview waktu auto-buka, opsi radio `30 Menit`, `60 Menit`, `Sepanjang Hari`, dan `Durasi lain`).
- Mengintegrasikan Custom Date & Time Picker popover lengkap: navigasi bulan kalender, proteksi tanggal lampau & batas maksimal 6 bulan, dropdown jam:menit WIB, dan tombol Batal/Pilih.
- Memperbaiki penanganan visibilitas modal overlay (`.active`, `hidden`, `aria-hidden`) agar interaksi switch toggle pada halaman Virtual Brand berjalan mulus tanpa terblokir.

Virtual Brand Link Level Placement & Card UI Optimization:
- Tombol **Link Brand** (`admin-table-brand-link`) dipindahkan dari level kartu outlet (`.vb-store-row`) ke level header kartu brand (`.vb-brand-card-head` / `.vb-group-identity`), berdampingan dengan pill status grup (`.vb-status-pill`).
- Tabel outlet desktop (`.vb-store-table`) disederhanakan dari 7 kolom menjadi 6 kolom (`Portal`, `Nama Listing`, `Store ID`, `Status`, `Jam Hari Ini`, `Link OFD`).
- Header whitespace dan margin bawah halaman VB dioptimalkan untuk tampilan desktop dan mobile yang bersih dan padat.

Virtual Brand Notification Direction & Evaluation Determinism:
- Pada mode Brand Toggle (`is_brand_toggle == True`), penentuan jenis notifikasi Discord (`summary_action` dan `is_open`) di `main-vb/src/db.py` **100% dipandu oleh `applied_status` brand** (`applied_status == "ON"` -> `ACTION_OPEN` / DIBUKA; `applied_status == "PAUSED"` -> `ACTION_CLOSE` / DITUTUP), mengeliminasi kontaminasi sisa log aksi patroli lama via `any()`.
- Pada mode Auto-Guarding (`is_brand_toggle == False`), penentuan arah notifikasi dihitung dari dominasi aksi aktual (`open_count >= close_count`) dengan fallback ke `applied_status`.
- Saat status toggle baru diaplikasikan pada brand (`apply_all_pending_statuses` & `apply_pending_status_if_needed`), buffer `_PENDING_BRAND_ACTIONS[brand_id]` dibersihkan secara atomik sebelum eksekusi dimulai.

Public Virtual Brand Dashboard Toggle UUID & Response Resilience:
- Toggle status brand dari Dashboard Publik Virtual Brand (`/brand/{slug}`) menetapkan `requested_by = NULL` pada tabel `vb_brands` untuk memenuhi batasan tipe data `UUID` PostgreSQL (`dashboard_accounts.id`).
- Parsing respons pada frontend `brand_dashboard.html` menerapkan penanganan asinkron yang aman (`try/catch` pada `res.json()`) untuk mencegah crash akibat respons error berformat non-JSON dari server.

Immediate Brand-Completion Notification Delivery:
- Notifikasi Discord Virtual Brand (`send_discord_vb_group_summary`) dikirimkan secara **instan (< 1-2 detik)** begitu seluruh outlet yang menjadi target aksi dari suatu brand selesai dieksekusi lintas portal, tanpa harus menunggu seluruh siklus keliling patroli (`Cycle`) selesai.
- Penahanan notifikasi (*hold buffer*) tetap aktif selama masih ada outlet milik brand tersebut di portal lain yang belum selesai diproses, menjamin agregasi atomik tetap terjaga 1 pesan per brand.
- Pelacakan dilakukan via `get_pending_brand_ids()` dan `get_brand_store_ids()` di `main-vb/src/db.py`, lalu di-flush spesifik via `db.flush_pending_brand_notifications(brand_ids=completed_brands)` di dalam perulangan `main-vb/src/daemon.py`.

ShopeeFood Hyperlink in Virtual Brand Discord Notifications:
- Seluruh pesan notifikasi Discord bot Virtual Brand (`send_discord_vb_group_summary`) menyertakan tautan ShopeeFood `[Link]` di sebelah kanan Store ID (`✅ Nama Outlet — <store_id> • [Link](https://shopee.co.id/universal-link/now-food/shop/<store_id>)`), baik pada mode Brand Toggle maupun Auto-Guarding (pada daftar berhasil maupun gagal).
- Jika item tidak memiliki Store ID, format fallback tetap bersih tanpa menghasilkan broken/empty link.

Virtual Brand Dedicated Dashboard UI Simplification:
- Hero Card Brand (`/brand/{slug}`) tampil bersih (*clean*) dan minimalis tanpa kartu metrik status live ("Live Buka", "Perlu Cek", "Live Tutup") dan tanpa accordion tombol/tabel detail outlet.
- Tombol aksi Hero Card berfokus penuh pada tombol "Lihat Jadwal" yang membentang rapi secara full-width bersama 3-state switch toggle status brand.

Dynamic Agency Summary Metric Cards:
- Kartu metrik ringkasan pada Tab Agency (`#metricTotal`, `#metricOpen`, `#metricClosed`) diperbarui secara dinamis via `updateAgencyStatCards(baseFiltered)` setiap kali pengguna menerapkan filter pencarian, filter pemilik, filter outlet, filter Store ID, maupun filter status, menjaga konsistensi perilaku dengan Tab Virtual Brand (VB).

Virtual Brand Discord Notification Mode Separation (Group Toggle vs Auto-Guarding):
- Pemicu Brand Control Toggle (User/Timed Expiry): Notifikasi Discord dikirimkan secara **kolektif** (`VB GROUP BERHASIL DIBUKA/DITUTUP BOT`) yang merekap seluruh outlet di bawah brand group.
- Pemicu Auto-Guarding Keliling (Routine Patrol Recovery): Notifikasi Discord dikirimkan secara **targeted** (`VB OUTLET (GUARDING) BERHASIL DIBUKA/DITUTUP BOT`) yang hanya menampilkan outlet yang diintervensi oleh bot patroli, mencegah kebingungan persepsi operasional seolah seluruh grup terdampak.
- Pelacakan pemicu dikelola via `_BRAND_TOGGLED_IDS` di `main-vb/src/db.py` dan di-flush di akhir siklus daemon.

Shopee Special Hours Schedule Gate & Priority Evaluation:
- Jadwal Khusus Shopee (`shopee_special_hours`) memiliki prioritas lebih tinggi daripada Jadwal Reguler (`shopee_regular_hours`).
- Jika outlet berada dalam periode Jadwal Khusus Tutup (`date_type=1` atau di luar interval buka khusus):
  - Toggle switch pada dashboard (Admin, Mitra, dan Virtual Brand) otomatis berstatus `disabled`, terkunci di posisi kiri (`state-closed`), berwarna abu-abu (*gray*), dan menampilkan status pill `Sedang Tutup • Jadwal Khusus`.
  - Bot patroli (`bot-oc` dan `bot-vb`) menetapkan `target_state = TARGET_CLOSE` dan `action = ACTION_NO_CHANGE` (atau `ACTION_CLOSE` jika live status masih buka) tanpa mencoba membuka paksa outlet.

Virtual Brand Discord Notification Aggregation:
- Notifikasi Discord Virtual Brand (`send_discord_vb_group_summary`) dikirimkan secara atomik per-siklus penuh daemon (`daemon.py`), bukan per-portal individual, untuk mencegah pengiriman rekap bertahap ("mencicil") pada brand multi-portal.
- Trigger flush notifikasi dieksekusi di akhir siklus evaluasi daemon via `db.flush_pending_brand_notifications()`, sedangkan handler `db.record_log("SYSTEM")` di worker per-portal hanya mencatat log internal tanpa memicu pengiriman webhook ke Discord.

Virtual Brand Dedicated Dashboard & Link Brand Integration:
- Setiap brand Virtual Brand memiliki dashboard publik mandiri via slug URL `/brand/{slug}` yang dapat diakses langsung oleh PIC brand tanpa memerlukan halaman login password.
- Brand Hero Card menampilkan nama brand, switch toggle 3-state tanpa label teks, 3 metrik status live (Live Buka, Perlu Cek, Live Tutup), serta 2 tombol aksi di dalam Hero Card ("Lihat Jadwal" dan "Daftar Outlet (N)").
- Daftar outlet ditampilkan dalam format accordion collapsible yang terintegrasi di dalam Hero Card dengan isi 2 kolom ringkas: Nama Outlet (listing/portal & Store ID) dan Status Live/Bot (tanpa link ShopeeFood di dashboard brand).
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
