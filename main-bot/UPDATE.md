# Server Update Guide

## Repository alignment

Repository ini adalah project main-bot:

- GitHub: SuperfoodTech/bot-oc-prod
- Branch production: main
- Latest main-bot commit: 0da70eb
- Frontend repository: SuperfoodTech/dashboard-bot

Jangan melakukan perubahan frontend HTML di repository ini. Frontend berada di repository dashboard-bot.

## Service architecture

Backend API dan bot harus berjalan sebagai service terpisah:

- backend: port 8080
- bot: port 8081
- db: PostgreSQL

Backend API tidak boleh mengimpor atau menjalankan worker/browsers secara langsung.

Bot tidak boleh menjalankan Backend API. Bot hanya menjalankan daemon, worker, browser automation, dan Bot Control API.

Service di docker-compose.yml:

- db
- bot
- backend

Backend dan bot berbagi PostgreSQL melalui DATABASE_URL.

## PostgreSQL production

Production database:

    168.144.143.203:5555

Environment yang wajib tersedia pada backend dan bot:

    DATABASE_URL=postgresql://USER:PASSWORD@168.144.143.203:5555/botshopee?sslmode=require
    DB_ENCRYPTION_KEY=<fernet-key>

Jangan menulis password atau DB_ENCRYPTION_KEY ke Git, log, atau dokumentasi.

Firewall PostgreSQL harus membatasi akses hanya dari server aplikasi.

## Database migrations

Migration berada di:

    database/migrations/

Migration yang sudah tersedia:

1. 001_initial_schema.sql
2. 002_operational_fields.sql
3. 003_remove_short_name.sql

Migration 003 menghapus kolom short_name. Nama outlet sekarang hanya menggunakan long_name.

Untuk database baru, jalankan seluruh migration secara berurutan.

Untuk database production yang sudah pernah dibuat, jalankan migration baru secara manual setelah backup dan validasi koneksi. Jangan menjalankan ulang migration lama secara sembarangan.

## Spreadsheet migration

Google Spreadsheet hanya digunakan sebagai sumber import awal.

Import dilakukan dengan:

    PYTHONPATH=src uv run python src/migrate_spreadsheet.py --dry-run
    PYTHONPATH=src uv run python src/migrate_spreadsheet.py

Setelah import selesai, worker membaca PostgreSQL melalui db.py. Worker tidak boleh membaca Google Spreadsheet setiap siklus.

Credential akun Shopee dienkripsi menggunakan DB_ENCRYPTION_KEY.

## Admin onboarding

Tombol Tambah Mitra di frontend memanggil:

    POST /api/v1/admin/outlets

Endpoint ini membuat data merchant, portal, akun Shopee, outlet, subscription, operating hours, dashboard account, dan audit log dalam satu proses database.

Field utama:

- nama_pemilik
- nama_portal
- merchant_id
- store_id
- nama_panjang_outlet
- username
- phone
- password
- dashboard_password
- paket
- tanggal_mulai_layanan
- tanggal_berakhir_layanan

Store ID harus unique.

## Deployment

Update backend tanpa restart bot:

    docker compose up -d --build backend

Update bot tanpa restart backend:

    docker compose up -d --build bot

Cek status:

    docker compose ps
    docker compose logs --tail=100 backend
    docker compose logs --tail=100 bot

Healthcheck backend:

    curl http://127.0.0.1:8080/api/v1/health

Bot control healthcheck:

    curl http://127.0.0.1:8081/health

## Safety rules

- Jangan menggunakan git reset --hard pada server tanpa backup.
- Pull hanya jika working tree bersih.
- Backup PostgreSQL sebelum migration production.
- Jangan menjalankan browser automation saat validasi backend.
- Gunakan dry-run bot sebelum mengaktifkan action live.
- Jangan mengubah status subscription atau suspension langsung melalui SQL tanpa audit.
- Setelah deployment, cek backend dan bot secara terpisah.
