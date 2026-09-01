# SOP / Runbook FoodMaster Bot O/C

## 1. Tujuan

Dokumen ini merangkum hasil pembacaan codebase, brief produk, migrasi database, dan flow runtime repo `bot-oc` per 1 September 2026.

Fokus dokumen ini adalah runtime yang benar-benar aktif saat ini, bukan asumsi dari dokumen lama.

## 2. Ringkasan codebase aktif

| Komponen | Path utama | Fungsi | Catatan runtime |
|---|---|---|---|
| Monolith web | `src/backend/main.py` | FastAPI untuk admin dashboard, mitra dashboard, REST API, SSE | Jalan di port `3001` |
| Data access | `src/backend/db.py` | Inisialisasi schema, query operasional, status outlet, log, akun | Source of truth runtime adalah PostgreSQL |
| Bot Agency / outlet reguler | `main-bot/src/daemon.py`, `main-bot/src/worker.py` | Patroli outlet reguler, fetch jadwal Shopee, open/close outlet | Kontrol HTTP internal di port `8081` |
| Bot Virtual Brand | `main-vb/src/daemon.py`, `main-vb/src/worker.py`, `main-vb/src/db.py` | Patroli grup VB dan apply `requested_status` menjadi `applied_status` | Menggunakan DB yang sama |
| Import Agency | `scripts/import_sheet.py`, `src/core/import_sheet.py` | Ambil CSV Google Sheet Agency lalu simpan ke PostgreSQL | Import manual |
| Import / control VB | `src/backend/vb.py` | Ambil matrix VB, buat mapping brand-store, expose endpoint admin VB | CSV VB dipisah tab `gid=401458905` |
| Shopee browser/session | `src/core/browser.py` | Login Selenium, reuse session, extract token | Dipakai bot |
| Shopee runtime probes | `src/shopee/store_status.py` | Fetch live state, fetch regular hours, kirim open/pause XHR | Ada guard `StoreIdentityMismatch` |
| Template frontend | `src/backend/templates/*`, `src/backend/static/*` | UI admin dan mitra | Satu origin dengan backend |

Catatan penting:

- `main-agency/` dan `src/agency/` tidak lagi menjadi sumber acuan runtime karena di repo ini praktis hanya tersisa artefak `__pycache__`, bukan source `.py` aktif.
- `main-bot/src/db.py` hanya me-reexport `src/backend/db.py`.
- `main-vb/src/api.py` adalah API legacy dan default-nya dinonaktifkan.

## 3. Fakta implementasi aktual yang perlu diketahui

1. Runtime source of truth sekarang adalah PostgreSQL, bukan Google Sheet. Google Sheet hanya dipakai untuk import master data.
2. Port PostgreSQL lokal yang dipakai compose dan kode aktif adalah `5435`. Beberapa dokumen lama masih menyebut `5434`.
3. Endpoint admin untuk tambah outlet, edit outlet, suspend outlet, dan renew subscription masih ada, tetapi hard-disabled dengan respons `403`. Brief V3 yang mewajibkan edit master data via Google Sheet memang konsisten dengan perilaku ini.
4. Hapus outlet masih aktif. Flow-nya tidak langsung delete DB: backend mencoba menulis balik ke Google Apps Script dulu untuk menandai row sebagai `Nonaktif`, baru menghapus record di PostgreSQL.
5. Endpoint `POST /api/v1/sync` tidak lagi menjalankan aksi Shopee. Endpoint ini sekarang hanya mengembalikan snapshot status runtime. Aksi ke Shopee hanya dijalankan daemon bot.
6. Password dashboard dan password Shopee masih disimpan plaintext pada `dashboard_accounts.password_plain` dan `shopee_accounts.password_plain`.
7. Bot reguler hanya memproses username yang lolos `ALLOWED_USERNAMES`, default `auto7313`.
8. Bot VB memakai credential runtime dari file/env VB, walaupun importer backend masih menulis placeholder akun `auto7313` saat membuat outlet VB baru.

## 4. Alur bisnis berbasis database

### 4.1 Agency / outlet reguler

1. Tim mengelola master data di Google Sheet Agency.
2. Admin menekan `Fetch dari Sheet` atau memanggil `POST /api/v1/admin/sync-source`.
3. Importer membuat atau mengupdate data pada `merchants`, `portals`, `dashboard_accounts`, `shopee_accounts`, `outlets`, `outlet_states`, `subscriptions`, dan `operating_hours`.
4. Admin dan mitra hanya mengubah control state runtime: `vercel_status`, `pause_until`, dan audit log.
5. Bot reguler membaca outlet aktif dari PostgreSQL, lalu per portal:
   - memastikan browser/session siap,
   - fetch regular hours Shopee,
   - fetch live state Shopee,
   - mengevaluasi decision engine,
   - mengirim aksi open/close jika perlu,
   - menyimpan hasil ke `outlet_states`, `automation_logs`, dan `automation_errors`.
6. UI admin/mitra membaca status runtime dari PostgreSQL dan menerima update live via SSE.

### 4.2 Virtual Brand

1. Tim mengelola matrix VB di tab Sheet terpisah.
2. Admin menekan `Fetch dari Sheet` saat tab `Virtual Brand` aktif atau memanggil `POST /api/v1/admin/vb/import`.
3. Importer VB membuat atau mengupdate:
   - `vb_brands`
   - `vb_brand_outlets`
   - outlet placeholder jika `store_id` belum ada di `outlets`
4. Saat admin men-toggle brand, backend hanya menyimpan `requested_status` dan opsional `requested_pause_until`.
5. Daemon VB yang bertugas mengubah pending request itu menjadi `applied_status` saat brand mendapat giliran patroli.
6. Setelah `applied_status` siap, worker VB memproses store-store anggota brand per portal merchant, lalu mencatat hasilnya ke log mode `VB`.

### 4.3 Urutan keputusan bot

Urutan keputusan di `core/decision.py` untuk outlet reguler adalah:

1. Penangguhan admin (`SUSPENDED`) -> target selalu tutup.
2. Subscription expired -> Auto Open tidak boleh membuka outlet.
3. Pause aktif (`pause_until` masih di masa depan) -> outlet tetap tutup sementara.
4. Jadwal reguler Shopee -> bot hanya boleh memproses buka pada jam yang valid.
5. Toggle kontrol (`vercel_status`) -> `ON` berarti target buka, `OFF` berarti target tutup.
6. Live state Shopee dibandingkan dengan target -> hasil akhir `NO_CHANGE`, `ACTION_OPEN`, atau `ACTION_CLOSE`.

Untuk Virtual Brand, status layanan dan penangguhan tidak dipakai sebagai gate. Target utamanya datang dari `vb_brands.applied_status` / `requested_status`.

### 4.4 Status runtime penting

| Domain | Nilai utama | Arti |
|---|---|---|
| `vercel_status` | `ON`, `OFF` | Desired control status dari dashboard |
| `shopee_actual_status` | `ON`, `PAUSE`, `CLOSED`, `UNKNOWN` | Live state terakhir dari Shopee |
| `schedule_fetch_status` | `NOT_FETCHED_YET`, `FETCH_RETRYING`, `FETCHED_EMPTY`, `READY` | Kondisi cache jadwal reguler Shopee |
| `bot_phase` | `IN_SYNC`, `PENDING_OPEN`, `PENDING_PAUSE`, `WAITING_SCHEDULE`, `STATUS_UNKNOWN`, dll | Fase yang ditampilkan UI |
| `display_toggle_reason` | `READY`, `OUTSIDE_SCHEDULE`, `SUSPENDED`, atau salah satu nilai `schedule_fetch_status` | Alasan toggle terlihat aktif/nonaktif/terkunci |

## 5. Peta tabel PostgreSQL yang dipakai runtime

| Tabel | Peran | Writer utama | Reader utama |
|---|---|---|---|
| `merchants` | Pemilik / mitra | importer Agency, helper `_context` | dashboard, bot |
| `portals` | Merchant portal Shopee | importer Agency, importer VB | dashboard, bot |
| `shopee_accounts` | Akses akun Shopee | importer Agency, importer VB | bot reguler, bot VB |
| `dashboard_accounts` | Admin dan mitra login | `init_db`, generate link, helper `_context`, settings admin | admin login, user login |
| `outlets` | Identitas Store ID | importer Agency, importer VB | dashboard, bot |
| `outlet_states` | Toggle, live state, pause, timezone, jadwal Shopee | dashboard, bot, import bootstrap | dashboard, bot |
| `operating_hours` | Jadwal internal hasil import Agency | importer Agency | terbatas; decision runtime sekarang mengutamakan jadwal Shopee |
| `subscription_plans` | Master paket 3/6/12 bulan | migration seed | importer, dashboard |
| `subscriptions` | Masa aktif layanan outlet reguler | importer Agency, renew manual lama | decision engine, dashboard |
| `automation_logs` | Audit semua aksi dan patrol result | dashboard toggles, bot reguler, bot VB | dashboard logs, bot status |
| `automation_errors` | Error operasional ringkas | `record_log` saat aksi gagal | tab logs |
| `admin_audit_logs` | Audit perubahan admin / VB | backend admin, VB apply/import | investigasi |
| `vb_brands` | Desired/applied state brand VB | importer VB, admin VB, daemon VB | dashboard VB, bot VB |
| `vb_brand_outlets` | Mapping brand ke outlet | importer VB | dashboard VB, bot VB |
| `vb_patrol_runs` | Jejak siklus patroli VB | bot VB | logs / diagnosa |
| `vb_brand_runtime_status` | Ringkasan patroli brand VB | bot VB | dashboard logs |
| `system_settings` | Konfigurasi kunci-nilai sederhana | backend | backend |

## 6. Variabel environment minimum

| Variabel | Wajib | Keterangan |
|---|---|---|
| `DATABASE_URL` | Ya | Default lokal: `postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster` |
| `APP_BASE_URL` | Ya | Dipakai untuk membuat link dashboard mitra |
| `GOOGLE_SHEETS_CSV_URL` | Ya untuk import Agency | Sumber CSV master Agency |
| `GOOGLE_SHEETS_APPS_SCRIPT_URL` | Ya untuk hapus outlet | Web App untuk menandai row Sheet jadi `Nonaktif` |
| `GOOGLE_SHEETS_APPS_SCRIPT_TOKEN` | Ya untuk hapus outlet | Token write-back Apps Script |
| `SHOPEE_BOT_USERNAME` | Ya untuk bot reguler | Default `auto7313` |
| `SHOPEE_BOT_PASSWORD` | Ya untuk bot reguler | Password akun Shopee bot reguler |
| `ALLOWED_USERNAMES` | Direkomendasikan | Whitelist akun Shopee yang boleh diproses |
| `HEADLESS` | Direkomendasikan | Mode Chromium headless untuk bot |
| `VB_SESSION_FILE` | Ya untuk bot VB | Session file VB |
| `VB_CREDENTIALS_FILE` | Ya untuk bot VB | Credential file VB |
| `VB_SHOPEE_USERNAME` | Opsional | Fallback username VB jika credential file tidak ada |
| `GOOGLE_AUTH_ENABLED` | Opsional | Jika `true`, aktifkan flow OAuth Google |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Opsional | Wajib hanya jika Google Auth diaktifkan |

## 7. Startup lokal yang direkomendasikan

### 7.1 Siapkan dependency

```bash
cd /home/akbarhann/project/bot-oc
uv sync
cp .env.example .env
```

### 7.2 Jalankan PostgreSQL

```bash
docker compose up -d db
```

### 7.3 Import Agency dari Google Sheet

```bash
DATABASE_URL=postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster \
PYTHONPATH=src \
uv run python scripts/import_sheet.py
```

### 7.4 Jalankan monolith web

Pilihan 1, lokal non-container:

```bash
./scripts/dev.sh
```

Pilihan 2, container:

```bash
docker compose up -d --build web
```

### 7.5 Jalankan bot reguler dan VB

```bash
docker compose up -d --build bot bot-vb
```

## 8. SOP operasional harian

### 8.1 Checklist awal shift

1. Pastikan database hidup:

```bash
docker compose ps
```

2. Pastikan monolith sehat:

```bash
curl -s http://localhost:3001/api/v1/health
```

3. Login ke admin dashboard di `/admin/login`.
4. Buka tab `Logs` dan cek apakah event reguler / VB masih bergerak.
5. Cek `Bot Status` pada dashboard admin. Jika offline, lanjut ke bagian troubleshooting.

### 8.2 Refresh data Agency dari Sheet

1. Pastikan perubahan master data sudah selesai di Google Sheet Agency.
2. Di tab `Operasional Outlet`, klik `Fetch dari Sheet`.
3. Verifikasi outlet muncul di tabel dan filter.
4. Jika import gagal, cek log response dan periksa duplikasi `store_id`.

### 8.3 Refresh data Virtual Brand dari Sheet

1. Pindah ke tab `Virtual Brand`.
2. Klik `Fetch dari Sheet`.
3. Pastikan ringkasan import menampilkan jumlah brand aktif, brand yang diaktifkan/dinonaktifkan, serta store yang terhubung.
4. Jika ada `portal_mismatches`, cek mapping portal di database vs kolom sheet VB.

### 8.4 Operasikan outlet reguler

1. Gunakan filter owner, outlet, store ID, status, subscription, atau paket.
2. Untuk membuka outlet, aktifkan toggle `ON`.
3. Untuk menutup sementara outlet, matikan toggle lalu pilih durasi:
   - `30 Menit`
   - `60 Menit`
   - `Sepanjang Hari`
   - `Durasi lain`
4. Pahami bahwa `ON` hanya menyimpan desired state. Outlet bisa tetap terlihat tutup sampai bot selesai patroli.

### 8.5 Operasikan Virtual Brand

1. Buka tab `Virtual Brand`.
2. Filter brand, portal, atau store ID.
3. Toggle brand ke `ON` atau `OFF`.
4. Untuk bulk action, klik `Pilih beberapa`.
5. Status brand yang baru diubah akan masuk `requested_status` dulu dan baru diterapkan saat daemon VB memproses brand tersebut.

### 8.6 Pantau aktivitas bot

1. Buka tab `Logs`.
2. Lihat dua hal:
   - `summary` reguler dan VB selama 24 jam,
   - daftar `errors` terbaru.
3. Gunakan filter mode dan pencarian bila perlu.
4. Gunakan panel `Bot Activity` untuk melihat cycle terakhir, stores processed, dan countdown next cycle.

### 8.7 Hapus outlet

1. Pastikan outlet memang harus dihentikan permanen.
2. Gunakan aksi hapus di dashboard admin.
3. Backend akan:
   - memanggil Apps Script untuk menandai row master data sebagai `Nonaktif`,
   - menghapus data outlet dari PostgreSQL,
   - menghapus merchant terkait jika outlet itu outlet terakhir milik merchant tersebut.
4. Jika Apps Script gagal, penghapusan dibatalkan.

## 9. Runbook command-line penting

### 9.1 Lihat log service

```bash
docker compose logs --tail=100 web
docker compose logs --tail=100 bot
docker compose logs --tail=100 bot-vb
```

### 9.2 Restart service tertentu

```bash
docker compose restart web
docker compose restart bot
docker compose restart bot-vb
```

### 9.3 Rebuild hanya web tanpa menyentuh bot

```bash
docker compose build web
docker compose up -d --no-deps web
```

### 9.4 Deploy seluruh stack

```bash
./scripts/prod.sh
```

## 10. Troubleshooting

### 10.1 `Fetch dari Sheet` gagal

Penyebab umum:

- `GOOGLE_SHEETS_CSV_URL` salah atau sheet tidak bisa diakses.
- Ada `store_id` duplikat di sheet Agency.

Langkah:

```bash
curl -I "$GOOGLE_SHEETS_CSV_URL"
DATABASE_URL=postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster PYTHONPATH=src uv run python scripts/import_sheet.py
```

### 10.2 Toggle terkunci

Arti status paling umum:

- `NOT_FETCHED_YET`: bot belum pernah berhasil fetch jadwal Shopee.
- `FETCH_RETRYING`: bot sudah mencoba fetch dan gagal; akan retry.
- `FETCHED_EMPTY`: jadwal reguler Shopee memang belum diatur di Shopee.
- `OUTSIDE_SCHEDULE`: sekarang di luar jam operasional Shopee.
- `SUSPENDED`: outlet ditahan admin.

### 10.3 Bot reguler tidak mau start

Penyebab umum:

- stale lock `main-bot/src/daemon.lock`
- port `8081` dianggap sudah dipakai
- browser/session rusak

Langkah:

```bash
rm -f main-bot/src/daemon.lock
docker compose restart bot
```

### 10.4 Bot VB tidak memproses brand

Cek hal berikut:

1. `bot-vb` hidup.
2. `vb_brands.is_active=true`.
3. `requested_status` sudah berubah menjadi `applied_status`.
4. session dan credential VB benar.

### 10.5 Outlet hilang dari daftar Agency

Outlet reguler di query utama akan dikeluarkan jika:

- `outlets.is_active=false`, atau
- outlet menjadi anggota `vb_brand_outlets`

Jadi outlet yang dipindahkan ke scope VB memang tidak akan muncul lagi di dashboard Agency.

### 10.6 Error `ModuleNotFoundError` saat pakai `python`

Gunakan `uv run ...` atau `./scripts/dev.sh`. Repo ini tidak mengandalkan Python sistem polos.

## 11. Gap implementasi yang perlu diawasi

1. Password masih plaintext di database.
2. Sebagian UI admin untuk create/edit/suspend/renew masih tampil, tetapi backend sudah menolak aksinya.
3. Ada jejak dokumen lama yang masih menyebut SQLite, port `5434`, atau flow sheet sebagai runtime source of truth. Untuk operasi harian, ikuti perilaku code aktif di repo ini.
4. API legacy VB di `main-vb/src/api.py` tidak boleh dijadikan jalur kontrol utama kecuali environment secara sengaja mengaktifkannya.
