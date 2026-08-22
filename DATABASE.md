# Database Context for Agents

## Project boundaries

- `main-bot/` berisi backend dan bot.
- `web/` berisi frontend HTML.
- PostgreSQL adalah target database baru.
- OTP tidak termasuk dalam database atau skema baru.

Di repository ini, source backend saat ini berada di `src/`. Folder `web/` adalah repository frontend terpisah dan dapat memiliki salinan file lama.

## Current database state

PostgreSQL sudah disiapkan, tetapi aplikasi belum dialihkan dari SQLite.

- Adapter aktif saat ini: `src/backend/db.py` menggunakan SQLite.
- Target adapter: PostgreSQL.
- Migration awal: `database/migrations/001_initial_schema.sql`.
- ERD: `erd.md`.
- PostgreSQL development service: `fm-postgres`.
- PostgreSQL development port: `127.0.0.1:5434`.
- Database default: `foodmaster`.
- PostgreSQL production: `168.144.143.203:5555`.

Jangan mengganti adapter SQLite ke PostgreSQL secara parsial. Perubahan adapter harus dilakukan sebagai satu tahap migrasi yang mencakup koneksi, query, seed/import, testing, dan fallback/error handling.

## Local setup

Salin konfigurasi contoh ke environment lokal dan gunakan password lokal yang kuat:

```bash
cp .env.example .env
docker compose up -d db
```

Compose akan menjalankan migration dari:

```text
database/migrations/
```

Connection string lokal:

```text
postgresql://foodmaster:<PASSWORD>@localhost:5434/foodmaster
```

Catatan: script init PostgreSQL Docker hanya otomatis dijalankan ketika data volume masih baru. Migration tambahan harus dibuat sebagai file baru, bukan mengubah migration yang sudah pernah dijalankan.

## Production connection

Production menggunakan:

```text
postgresql://foodmaster:<PASSWORD>@168.144.143.203:5555/foodmaster?sslmode=require
```

Jangan menulis password asli ke repository, commit, log, URL publik, atau dokumentasi. Gunakan environment/secret manager.

Akses port production wajib dibatasi firewall hanya untuk IP server aplikasi. Jangan membuka PostgreSQL ke seluruh internet. Gunakan `sslmode=require` hanya jika TLS PostgreSQL memang sudah dikonfigurasi.

## Schema overview

Relasi utama:

```text
merchants
  └── portals
        ├── shopee_accounts
        └── outlets
              ├── operating_hours
              ├── outlet_states
              ├── subscriptions
              ├── automation_logs
              └── admin_audit_logs

subscription_plans
  └── subscriptions

dashboard_accounts
  └── admin_audit_logs
```

Tabel utama:

- `merchants`: pemilik/merchant.
- `portals`: nama portal merchant.
- `shopee_accounts`: akses akun ShopeePartner dan Merchant ID.
- `outlets`: identitas outlet; `store_id` adalah identifier bisnis utama.
- `operating_hours`: jadwal per hari, satu baris per outlet per weekday.
- `subscription_plans`: paket 3, 6, dan 12 bulan.
- `subscriptions`: subscription dan riwayat perpanjangan.
- `outlet_states`: status operasional terbaru.
- `dashboard_accounts`: akun admin/merchant dengan password hash.
- `automation_logs`: setiap pengecekan dan tindakan bot.
- `admin_audit_logs`: perubahan penting yang dilakukan admin.

Semua outlet dianggap ShopeeFood. Jangan menambahkan kembali kolom `aplikator` atau `platform` tanpa keputusan baru.

## Spreadsheet mapping

Spreadsheet hanya digunakan sebagai sumber import awal. Kolom A tidak dimigrasikan.

| Kolom | Target |
|---|---|
| B Kepemilikan | Tidak digunakan; pemisahan VB memakai relasi `vb_brand_outlets` |
| C Paket | `subscriptions.plan_id` |
| D-E Tanggal layanan | `subscriptions.start_date`, `end_date` |
| F Nomor HP | `shopee_accounts.phone` |
| G-H Username/password | `shopee_accounts.username`, `password_encrypted` |
| I Nama Pemilik | `merchants.name` |
| J Nama Portal | `portals.name` |
| K Merchant ID | `shopee_accounts.merchant_id_external` |
| L Store ID | `outlets.store_id` |
| M-N Nama outlet | `outlets.long_name`, `short_name` |
| O Status Utama | `outlet_states.vercel_status` |
| P-Q Link/password dashboard | `dashboard_accounts` |
| R-X Jadwal | `operating_hours` |
| Y Jadwal khusus | `outlets.special_hours` |

Status subscription, penangguhan, dan status aktual ShopeePartner dikelola PostgreSQL, bukan dijadikan source of truth spreadsheet.

## Bot decision priority

Target outlet ditentukan dengan urutan:

1. Status penangguhan.
2. Subscription Auto Open masih aktif.
3. Vercel Toggle sebagai source of truth.
4. Jam operasional.
5. Status aktual ShopeePartner.

Jika status aktual berbeda dari target, bot menjalankan `OPEN_STORE` atau `CLOSE_STORE` dan menyimpan hasil ke `automation_logs`.

Subscription expired hanya menonaktifkan Auto Open. Subscription expired tidak otomatis mengubah outlet menjadi suspended.

## Security rules

- Password dashboard harus menggunakan hash.
- Password ShopeePartner harus terenkripsi atau disimpan di secret manager.
- Jangan menampilkan credential spreadsheet dalam output, log, test fixture, atau dokumentasi.
- Merchant hanya boleh melihat outlet milik merchant tersebut.
- Merchant tidak boleh mengubah status penangguhan.
- Status penangguhan hanya dapat diubah admin.
- Perubahan penting wajib masuk `admin_audit_logs`.
- Jangan memasukkan data OTP ke PostgreSQL.
- Jangan menjalankan migration production tanpa backup dan validasi koneksi.

## Migration rules for future agents

1. Jangan mengedit migration yang sudah dijalankan di environment.
2. Buat file migration baru dengan nomor berurutan.
3. Gunakan constraint dan index yang sesuai kebutuhan query.
4. Pertahankan `store_id` sebagai unique key bisnis.
5. Uji migration pada database kosong dan database yang sudah berisi data.
6. Pisahkan import data spreadsheet dari migration struktur tabel.
7. Jangan menghapus data production sebagai bagian dari migration tanpa persetujuan eksplisit.
8. Setelah adapter PostgreSQL aktif, tambahkan test integrasi PostgreSQL; jangan hanya mengandalkan test SQLite.

