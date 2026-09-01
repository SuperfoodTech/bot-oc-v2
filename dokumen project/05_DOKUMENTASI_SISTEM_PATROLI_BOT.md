# Dokumentasi Sistem Patroli Bot FoodMaster

## 1. Tujuan dokumen

Dokumen ini menjelaskan secara khusus cara kerja bot patroli pada repo `bot-oc`, berdasarkan implementasi aktif di codebase.

Fokusnya adalah:

- bagaimana bot reguler dan bot VB berjalan,
- data apa yang dibaca dari PostgreSQL,
- kapan bot memutuskan buka/tutup outlet,
- bagaimana scheduler menentukan giliran patroli,
- apa yang terjadi saat fetch jadwal atau live state gagal.

## 2. Gambaran arsitektur patroli

Ada dua service bot utama:

| Bot | Entry point | Scope |
|---|---|---|
| Bot reguler / Agency | `main-bot/src/daemon.py` | outlet reguler yang tidak menjadi anggota `vb_brand_outlets` |
| Bot Virtual Brand | `main-vb/src/daemon.py` | outlet yang dikontrol melalui `vb_brands` |

Keduanya memakai pola yang sama:

1. baca state dari PostgreSQL,
2. bangun antrean patroli,
3. siapkan session browser Shopee,
4. fetch jadwal reguler Shopee,
5. fetch live state Shopee,
6. evaluasi decision engine,
7. jalankan aksi open/close bila perlu,
8. simpan hasil patroli kembali ke database.

## 3. Source of truth yang dipakai bot

Bot tidak lagi membaca Google Sheet sebagai sumber keputusan harian.

Source of truth runtime bot adalah PostgreSQL, terutama:

- `outlets`
- `outlet_states`
- `subscriptions`
- `vb_brands`
- `vb_brand_outlets`
- `automation_logs`
- `automation_errors`

Google Sheet hanya dipakai untuk import master data ke database.

## 4. Komponen yang terlibat

### 4.1 Bot reguler

- `main-bot/src/daemon.py`
  Menjalankan loop patroli 24/7, menjaga single-instance lock, memulai bot control API, dan mengatur interval siklus.

- `main-bot/src/worker.py`
  Menjalankan patroli per grup merchant/portal, fetch jadwal Shopee, fetch live state, menjalankan action, dan mencatat hasil.

- `main-bot/src/scheduler.py`
  Menentukan outlet atau portal mana yang paling dulu dipatroli berdasarkan urgency.

- `src/backend/db.py`
  Menyediakan query runtime store, update state Shopee, update jadwal Shopee, dan log.

- `src/shopee/store_status.py`
  Menarik live state dan regular hours dari Shopee, serta mengirim action open/pause via XHR dalam browser.

- `src/core/browser.py`
  Mengelola login, session token, Chrome profile, dan merchant switching di dashboard Shopee.

### 4.2 Bot Virtual Brand

- `main-vb/src/daemon.py`
  Loop patroli VB.

- `main-vb/src/worker.py`
  Implementasi patrol VB yang pada dasarnya mengikuti pola worker bot reguler.

- `main-vb/src/db.py`
  Mengambil outlet anggota brand aktif, menerapkan `requested_status` menjadi `applied_status`, dan menyediakan data patrol untuk scope VB.

## 5. Bagaimana bot reguler memilih outlet yang dipatroli

Bot reguler tidak langsung looping outlet satu per satu secara flat.

Ia memakai grouping:

- kunci grup: `(username Shopee, nama_portal)`

Artinya:

- satu akun Shopee bisa punya beberapa portal,
- satu portal bisa punya beberapa outlet,
- bot akan switch merchant sekali, lalu memproses semua outlet dalam portal itu.

Ini penting karena:

1. lebih cepat,
2. mengurangi risiko salah konteks merchant,
3. lebih stabil untuk session browser Shopee.

## 6. Scheduler patroli

Scheduler aktif ada di `main-bot/src/scheduler.py`.

Ia memberi prioritas berdasarkan kondisi outlet. Contoh logika penting:

| Kondisi | Prioritas umum |
|---|---|
| outlet perlu segera dibuka | tertinggi |
| outlet perlu segera ditutup | sangat tinggi |
| pause aktif dan ada boundary sesi berikutnya | tinggi |
| jadwal Shopee belum tersedia | retry cepat |
| outlet buka dan in sync | heartbeat |
| outlet tidak butuh aksi | prioritas rendah |

Prinsipnya:

- mismatch live state vs desired state selalu diprioritaskan,
- boundary waktu seperti akhir pause atau awal sesi berikutnya bisa mengalahkan heartbeat biasa,
- bot tidak menunggu interval tetap bila ada event yang lebih mendesak.

## 7. Alur satu siklus bot reguler

### 7.1 Startup

Saat daemon bot reguler mulai:

1. membuat lock file agar tidak ada dua daemon berjalan bersamaan,
2. inisialisasi database/migrasi,
3. menyalakan bot control API di port `8081`,
4. melakukan warmup session browser Shopee untuk akun yang diizinkan.

### 7.2 Loop patroli

Setiap siklus:

1. bot cek apakah status sedang `paused`,
2. bot cek koneksi internet,
3. bot ambil semua outlet reguler aktif dari PostgreSQL,
4. bot bangun queue scheduler,
5. bot pilih merchant group yang paling due,
6. bot jalankan `worker.sync_all_stores(...)` untuk grup itu,
7. bot simpan hint kapan bangun berikutnya.

### 7.3 Di dalam worker

Untuk setiap portal merchant yang sedang diproses:

1. pastikan browser session masih hidup,
2. jika browser masih di merchant yang benar, pakai langsung,
3. jika konteks merchant salah, bot menjalankan switch merchant,
4. jika session mati, bot coba recovery session,
5. setelah itu bot memproses outlet satu per satu di portal tersebut.

## 8. Alur patroli per outlet

Untuk setiap outlet reguler:

1. bot masuk ke halaman Business Hours Shopee untuk `store_id` tersebut,
2. bot fetch regular hours dari endpoint Shopee,
3. bot fetch live state outlet dari endpoint Shopee,
4. bot validasi bahwa response memang milik `store_id` yang diminta,
5. baru setelah itu bot menjalankan decision engine,
6. bila perlu, bot kirim aksi `OPEN` atau `PAUSE/CLOSE`,
7. bot simpan log hasilnya.

Guard yang penting:

- jika response regular hours milik store lain, outlet dikarantina untuk cycle itu,
- jika response live state milik store lain, outlet juga dilewati,
- bot tidak boleh membuat keputusan dengan data yang tidak terpercaya.

## 9. Fetch jadwal Shopee

Regular hours Shopee sangat penting karena dashboard dan decision engine sekarang mengandalkannya.

Status fetch jadwal yang disimpan di `outlet_states.schedule_fetch_status`:

| Nilai | Arti |
|---|---|
| `NOT_FETCHED_YET` | belum pernah berhasil fetch |
| `FETCH_RETRYING` | pernah mencoba tetapi gagal |
| `FETCHED_EMPTY` | berhasil fetch tetapi jadwal Shopee kosong |
| `READY` | jadwal valid sudah tersedia |

Perilaku bot:

1. Jika fetch berhasil dan ada interval valid, bot simpan ke `shopee_regular_hours` dan status menjadi `READY`.
2. Jika fetch berhasil tetapi tidak ada interval aktif, bot simpan status `FETCHED_EMPTY`.
3. Jika fetch gagal dan belum ada jadwal valid lama, bot tandai `FETCH_RETRYING`.
4. Jika fetch gagal tetapi database masih punya jadwal valid lama, bot boleh mempertahankan cache jadwal lama itu untuk sementara.

## 10. Fetch live state Shopee

Live state diambil dari endpoint Shopee store dan dinormalisasi menjadi:

- `ON`
- `PAUSE`
- `CLOSED`
- `UNKNOWN`

Bot juga bisa menyimpan timezone outlet bila Shopee memberikannya.

Live state ini disimpan ke:

- `outlet_states.shopee_actual_status`
- `outlet_states.timezone`

## 11. Decision engine

Decision engine utama ada di `core/decision.py`.

Urutan keputusan outlet reguler:

1. cek suspension admin,
2. cek subscription expired,
3. cek pause aktif,
4. cek jadwal reguler Shopee,
5. cek toggle `vercel_status`,
6. bandingkan target dengan live state.

Output decision engine:

- `NO_CHANGE`
- `ACTION_OPEN`
- `ACTION_CLOSE`

Contoh:

| Desired | Live | Hasil |
|---|---|---|
| `OPEN` | `CLOSED` | `ACTION_OPEN` |
| `PAUSE` | `ON` | `ACTION_CLOSE` |
| `OPEN` | `ON` | `NO_CHANGE` |

## 12. Eksekusi aksi ke Shopee

Saat hasil decision adalah aksi:

1. worker memanggil `execute_outlet_shopee_action(...)`,
2. browser/session aktif dipakai untuk mengirim XHR in-browser,
3. untuk tutup sementara, bot dapat mengirim `pause_end_time`,
4. hasil sukses/gagal dicatat ke log.

Bot reguler default hanya mengeksekusi akun yang lolos whitelist `ALLOWED_USERNAMES`, biasanya `auto7313`.

## 13. Logging dan observability

Setelah patroli atau aksi:

- `automation_logs` menyimpan event dan alasan,
- `automation_errors` menyimpan error ringkas,
- `outlet_states` diperbarui,
- dashboard admin dan mitra menerima update via SSE jika ada perubahan state.

Bot control API di port `8081` juga menyediakan:

- `/health`
- `/bot/status`
- `/bot/activity`
- `/bot/start`
- `/bot/pause`
- `/bot/sync`
- `/bot/logs`

## 14. Cara kerja bot Virtual Brand

Bot VB mengikuti pola yang mirip, tetapi source control-nya berbeda.

### 14.1 Desired state VB

Desired state VB berasal dari:

- `vb_brands.applied_status`
- `vb_brands.requested_status`
- `vb_brands.pause_until`
- `vb_brands.requested_pause_until`

Admin dashboard tidak langsung mengubah live outlet VB. Yang dilakukan admin hanyalah menyimpan permintaan:

- `requested_status = ON` atau `PAUSED`

### 14.2 Apply pending status

Saat daemon VB berpatroli:

1. ia mencari brand aktif yang punya `requested_status`,
2. lalu mengubahnya menjadi `applied_status`,
3. `requested_status` dibersihkan,
4. perubahan itu dicatat ke audit log.

Jadi ada dua fase:

1. request disimpan,
2. request diterapkan saat brand mendapat giliran patroli.

### 14.3 Pengambilan outlet VB

Bot VB membaca outlet dari:

- `vb_brand_outlets`
- `vb_brands`
- `outlets`
- `portals`
- `outlet_states`

Jika satu `store_id` dipakai di lebih dari satu brand aktif, worker VB berusaha memakai state paling restriktif agar tidak ada brand `ON` yang diam-diam mengalahkan brand lain yang minta `OFF`.

## 15. Retry, recovery, dan fail-safe

Beberapa mekanisme perlindungan yang aktif:

### 15.1 Session recovery

Jika driver mati atau invalid:

- bot membuang session cache untuk akun itu,
- bot membuka session baru,
- bot login ulang atau memulihkan browser context.

### 15.2 Network gate

Jika internet tidak tersedia:

- siklus patroli dihentikan sementara,
- bot menunggu sebelum mencoba lagi.

### 15.3 Stale lock protection

Daemon memakai lock file agar tidak ada dua instance paralel yang berpatroli bersamaan.

### 15.4 Schedule quarantine

Jika response regular hours tidak cocok dengan `store_id` target:

- jadwal itu tidak dipakai,
- decision/action untuk outlet tersebut dilewati pada cycle itu.

### 15.5 Live-state quarantine

Jika response live state ternyata untuk outlet lain:

- bot juga tidak mengambil aksi untuk outlet tersebut.

## 16. Kapan bot bangun lagi

Bot tidak selalu tidur pada interval tetap.

Ia menghitung wake-up hint berdasarkan:

- outlet berikutnya yang due,
- boundary schedule berikutnya,
- berakhirnya pause aktif,
- kebutuhan verifikasi ulang mismatch,
- idle reevaluation maksimum.

Pada implementasi saat ini:

- bot tetap membatasi tidur panjang dengan reevaluasi ringan berkala,
- sehingga perubahan dashboard tidak perlu menunggu terlalu lama untuk mulai dipertimbangkan.

## 17. Hal yang penting dipahami operator

1. Toggle dashboard bukan aksi Shopee langsung. Toggle hanya mengubah desired state di database.
2. Outlet bisa sementara terlihat “belum sinkron” karena bot belum mendapat giliran patroli atau baru saja memproses request.
3. Status `Menunggu fetch jadwal` atau `Gagal fetch jadwal` berarti problem data schedule, bukan otomatis berarti bot mati.
4. `POST /api/v1/sync` pada monolith bukan pemicu aksi Shopee. Aksi live tetap milik daemon bot.
5. Untuk VB, perubahan status brand tidak langsung applied di saat tombol ditekan; status menunggu giliran patroli.

## 18. Known attention points

1. Ada perbedaan konfigurasi akun VB di beberapa area codebase: importer backend masih menulis placeholder `auto7313`, sementara runtime `bot-vb` cenderung memakai credential/file VB sendiri.
2. Password dashboard dan password Shopee masih plaintext di database.
3. Ada dokumen lama di repo yang masih menyebut arsitektur/port lama; untuk patroli bot, acuan yang lebih tepat adalah code aktif dan dokumen ini.

## 19. Ringkasan singkat

Secara sederhana, sistem patroli bot bekerja seperti ini:

1. database menentukan desired state,
2. bot membaca schedule dan live state dari Shopee,
3. scheduler memilih grup merchant paling prioritas,
4. decision engine menentukan perlu aksi atau tidak,
5. bot mengeksekusi open/close,
6. hasilnya kembali dicatat ke database dan diteruskan ke dashboard.
