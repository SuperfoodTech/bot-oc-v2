# FoodMaster — Skema dan Alur Bisnis

Dokumen ini adalah acuan arsitektur dan alur bisnis FoodMaster Auto Open/Auto Close.

## 1. Prinsip utama

- PostgreSQL adalah source of truth untuk runtime aplikasi.
- Google Spreadsheet hanya digunakan sebagai sumber import/master data awal.
- Dashboard admin dan dashboard mitra berada dalam satu monolith FastAPI.
- Bot automation adalah service independen yang membaca PostgreSQL.
- Akun Shopee bot bersama adalah `auto7313`.
- `merchant_name` digunakan untuk berpindah merchant/portal di Shopee.
- `store_id` adalah identitas outlet yang benar-benar dibuka atau ditutup.
- Satu merchant dapat memiliki banyak outlet.
- Suspension berlaku di level outlet, bukan merchant.
- Password masih plaintext pada fase awal sesuai keputusan produk.
- Bot tidak menutup browser setelah satu aksi; browser/session dipakai kembali untuk merchant dan outlet berikutnya.

## 2. Terminologi bisnis

| Istilah | Arti |
|---|---|
| Mitra | Pemilik akun dashboard FoodMaster, diwakili oleh `nama_pemilik` |
| Merchant | Grup bisnis milik mitra |
| Portal | Target merchant Shopee yang diwakili `merchant_name` |
| Outlet | Toko/cabang individual yang diwakili `store_id` |
| Bot account | Akun Shopee Partner yang digunakan bot, saat ini `auto7313` |
| Control status | Status ON/OFF yang dikendalikan dari dashboard |
| Actual status | Status aktual yang dibaca dari Shopee |

Dalam implementasi database saat ini, tabel `merchants` mewakili mitra/pemilik, sedangkan tabel `portals` menyimpan `merchant_name` Shopee.

## 3. Skema database

### 3.1 `merchants`

Menyimpan identitas pemilik/mitra.

| Kolom | Keterangan |
|---|---|
| `id` | Primary key internal |
| `name` | Nama pemilik/mitra, berasal dari kolom I |
| `is_active` | Status aktif mitra |

Satu `merchant` dapat memiliki banyak `portals` dan banyak `outlets`.

### 3.2 `dashboard_accounts`

Menyimpan akun dashboard mitra.

| Kolom | Keterangan |
|---|---|
| `merchant_id` | Relasi ke mitra |
| `username` | Identitas login dashboard |
| `password_plain` | Password dashboard pada fase awal |
| `link_slug` | Slug link dashboard mitra |
| `dashboard_url` | Link lengkap dashboard |
| `role` | `ADMIN` atau `MERCHANT` |

Satu akun dashboard mitra dapat melihat semua outlet milik mitra tersebut.

### 3.3 `portals`

Menyimpan target merchant/portal Shopee.

| Kolom | Keterangan |
|---|---|
| `merchant_id` | Mitra pemilik portal |
| `name` | `merchant_name`, digunakan saat switch merchant |
| `is_active` | Status portal |

Contoh:

```text
Mitra: Yolo
Portal: Do Eat, Gurame Bakar
Portal: SuperFood
```

### 3.4 `shopee_accounts`

Menyimpan konfigurasi akun Shopee yang digunakan untuk akses portal.

| Kolom | Keterangan |
|---|---|
| `portal_id` | Portal yang terkait |
| `username` | Username akses; runtime bot menggunakan `auto7313` |
| `password_plain` | Password akses pada fase awal |
| `phone` | Nomor pendukung login bila diperlukan |
| `session_file` | Lokasi session browser |
| `last_login_at` | Login terakhir |

Secara operasional, bot login menggunakan satu akun bersama:

```text
Username: auto7313
Password: Auto@7313
```

### 3.5 `bot_accounts`

Menyimpan entitas bot yang berjalan independen.

| Kolom | Keterangan |
|---|---|
| `username` | Username akun bot |
| `password_plain` | Password akun bot |
| `name` | Nama bot |
| `is_active` | Status bot |

### 3.6 `bot_merchant_assignments`

Mengelompokkan merchant yang menjadi tanggung jawab bot tertentu.

Relasi ini bukan pengecekan apakah merchant sudah terhubung di Shopee. Relasi ini hanya digunakan untuk:

- grouping target bot;
- membatasi scope bot;
- mendukung beberapa akun bot di masa depan.

### 3.7 `outlets`

Menyimpan identitas outlet yang menjadi target aksi.

| Kolom | Keterangan |
|---|---|
| `merchant_id` | Mitra pemilik |
| `portal_id` | Merchant/portal Shopee target |
| `shopee_account_id` | Akun akses portal |
| `store_id` | ID outlet Shopee, unik dan krusial |
| `long_name` | Nama panjang outlet |
| `special_hours` | Catatan jam khusus |
| `is_active` | Status outlet |

`short_name` tidak digunakan lagi.

Contoh:

```text
Mitra: WonderFood
Portal: WonderFood Malang
  - store_id: 1001
  - store_id: 1002
```

### 3.8 `outlet_states`

Menyimpan kondisi operasional outlet.

| Kolom | Keterangan |
|---|---|
| `outlet_id` | Satu state untuk satu outlet |
| `vercel_status` | Control status ON/OFF dari dashboard |
| `shopee_actual_status` | Status aktual di Shopee |
| `suspension_status` | `ACTIVE` atau `SUSPENDED` |
| `suspension_reason` | Alasan penangguhan |
| `pause_until` | Batas waktu pause sementara |
| `last_checked_at` | Pemeriksaan terakhir |
| `last_action_at` | Aksi terakhir |
| `updated_at` | Perubahan terakhir |

### 3.9 `operating_hours`

Menyimpan jam operasional reguler Senin–Minggu per outlet.

### 3.10 `subscription_plans`

Master paket layanan:

- Paket 3 Bulan
- Paket 6 Bulan
- Paket 12 Bulan

### 3.11 `subscriptions`

Menyimpan subscription per outlet.

Subscription sengaja berada di level outlet agar satu merchant dapat memiliki outlet aktif dan outlet menunggak secara bersamaan.

### 3.12 `automation_logs`

Menyimpan histori pemeriksaan dan aksi bot:

- status suspension;
- status subscription;
- status control sebelum aksi;
- status Shopee sebelum aksi;
- target status;
- action open/close;
- hasil sukses/gagal;
- alasan atau error.

### 3.13 `admin_audit_logs`

Menyimpan histori perubahan administratif seperti:

- membuat outlet;
- membuat link dashboard;
- mengubah suspension;
- memperbarui subscription.

## 4. Relasi data

```text
merchants (mitra/pemilik)
    │
    ├── dashboard_accounts
    ├── portals (merchant_name Shopee)
    │       └── shopee_accounts
    │
    └── outlets (store_id)
            ├── outlet_states
            ├── operating_hours
            └── subscriptions

bot_accounts (auto7313)
    └── bot_merchant_assignments ── merchants
```

## 5. Sumber data spreadsheet

Spreadsheet membaca kolom B–Y. Kolom A dihiraukan dan kolom setelah Y tidak digunakan.

| Kolom | Field | Perlakuan |
|---|---|---|
| B | Kepemilikan | Import master, tidak menentukan runtime |
| C | Paket | Subscription plan |
| D | Tanggal mulai layanan | Subscription |
| E | Tanggal berakhir layanan | Subscription |
| F | Nomor HP | Akses/login |
| G | Username | Data legacy/import |
| H | Password | Data legacy/import |
| I | Nama Pemilik | Mitra |
| J | Nama Portal | `merchant_name` |
| K | Merchant ID | Disimpan minimal/legacy, bukan identitas utama bot |
| L | Store ID | Identitas outlet utama |
| M | Nama Panjang Outlet | `long_name` |
| N | Nama Pendek Outlet | Tidak digunakan |
| O | Status Utama | Initial control status |
| P | Vercel Link | Link dashboard |
| Q | Vercel Password | Password dashboard |
| R–X | Jadwal | Jam operasional |
| Y | Jadwal Khusus | Catatan jam khusus |

Import dilakukan melalui:

```text
scripts/import_sheet.py
```

Setelah import, perubahan operasional dilakukan dari dashboard dan disimpan ke PostgreSQL.

## 6. Aturan keputusan bot

Bot mengevaluasi setiap outlet secara independen.

Urutan prioritas:

```text
1. Apakah outlet suspended?
   Ya  → target OFF

2. Apakah subscription expired?
   Ya  → target OFF

3. Baca control status dari dashboard
   ON  → target OPEN
   OFF → target CLOSE

4. Bandingkan dengan actual status Shopee
   Berbeda → jalankan aksi
   Sama    → NO_CHANGE
```

Status actual Shopee tidak menjadi source of truth. Status actual hanya digunakan untuk mengetahui apakah aksi diperlukan.

Jika dashboard ON, bot akan berusaha force open meskipun sebelumnya Shopee menutup outlet secara manual. Jika dashboard OFF, bot akan force close.

## 7. Alur dashboard admin

```text
Admin membuka dashboard
        │
        ▼
Membuat atau memilih mitra
        │
        ▼
Mendaftarkan merchant_name dan store_id
        │
        ▼
Data outlet disimpan ke PostgreSQL
        │
        ├── membuat/memperbarui subscription
        ├── membuat dashboard account mitra
        ├── menghubungkan merchant ke bot auto7313
        └── membuat state awal outlet
```

Admin dapat:

- melihat seluruh mitra dan outlet;
- membuat link dashboard mitra;
- suspend satu outlet;
- mengaktifkan kembali satu outlet;
- memperpanjang subscription satu outlet;
- melihat status actual dan log automation;
- mengontrol status bot.

## 8. Alur dashboard mitra

```text
Mitra membuka link dashboard
        │
        ▼
Login dengan password mitra
        │
        ▼
Melihat seluruh outlet miliknya
        │
        ▼
Mengubah toggle outlet ON/OFF
        │
        ▼
PostgreSQL menyimpan control status
        │
        ▼
Bot membaca perubahan pada siklus berikutnya
```

Mitra tidak dapat mengubah suspension atau subscription.

Jika mitra mencoba ON pada outlet yang suspended atau expired, sistem tetap menjaga target OFF.

## 9. Alur bot 24/7

```text
Bot start
   │
   ├── login/session akun auto7313
   ├── membaca merchant assignment dari DB
   └── membuka browser persistent

Setiap siklus:
   │
   ├── membaca outlet aktif dari PostgreSQL
   ├── mengelompokkan outlet berdasarkan merchant_name
   ├── switch merchant di browser yang sama
   ├── membaca/evaluasi status setiap store_id
   ├── force open atau force close bila diperlukan
   ├── menyimpan actual state dan log
   └── menunggu siklus berikutnya
```

Browser tidak ditutup setiap kali berpindah outlet. Browser hanya berakhir ketika bot dihentikan, crash, atau session perlu dipulihkan.

## 10. Development dan production

### Development

- PostgreSQL dapat dijalankan melalui Docker.
- Dashboard dapat dijalankan langsung dengan `scripts/dev.sh`.
- Bot dapat dijalankan sebagai process lokal atau container.
- Dashboard: `http://localhost:3001`.
- PostgreSQL host port: `5435`.

### Production

- Dashboard dan bot berjalan sebagai container terpisah.
- PostgreSQL memakai persistent volume dan tidak perlu diekspos ke internet.
- Komunikasi internal dashboard ke bot menggunakan `http://bot:8081`.
- Source code tidak di-bind mount ke container production.
- Reverse proxy menangani HTTPS dan domain publik.
- Secret production diberikan melalui environment/secret manager.

## 11. Batasan fase awal

Keputusan yang sengaja belum diperketat:

- Password belum di-hash/enkripsi.
- Belum ada multi-user kompleks dalam satu mitra.
- Belum ada dua bot account aktif paralel, tetapi relasinya sudah disiapkan.
- Spreadsheet belum menjadi sistem operasional dua arah.
- Merchant ID eksternal bukan identitas utama runtime.

Fokus fase ini adalah alur cepat, mudah diaudit, dan mudah digunakan oleh admin serta mitra.
