# FoodMaster Monolith — Walkthrough Lokal

## 1. Persiapan pertama kali

Pastikan Python 3.12+ tersedia, lalu dari folder project jalankan:

```bash
cd /home/akbarhann/project/bot-oc
uv sync
```

Spreadsheet adalah sumber import/master awal. Setelah di-import, PostgreSQL menjadi source of truth runtime; toggle, suspend, subscription, dan log bot tidak dibaca ulang dari spreadsheet.

## 2. Jalankan aplikasi

Gunakan satu command:

```bash
./scripts/dev.sh
```

Aplikasi dashboard berjalan sebagai satu proses FastAPI di port `3001`. Untuk menjalankan PostgreSQL dan bot dengan Docker:

```bash
docker compose up -d db
DATABASE_URL=postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster \
  PYTHONPATH=src uv run python scripts/import_sheet.py
docker compose up -d --build web bot
```

## 3. Buka dashboard

- Admin: http://localhost:3001
- User: http://localhost:3001/app
- Health check: http://localhost:3001/api/v1/health

Frontend dan API menggunakan origin yang sama. Tidak ada lagi service frontend terpisah atau port `8080`.

## 4. Data spreadsheet

Backend membaca kolom B–Y dan mengabaikan kolom A.

Urutan field yang digunakan:

```text
B Kepemilikan
C Paket
D Tanggal Mulai Layanan
E Tanggal Berakhir Layanan
F Akses No HP
G Akses Username
H Akses Kata Sandi
I Nama Pemilik
J Nama Portal
K Merchant ID
L Store ID
M Nama Panjang Outlet
N Nama Pendek Outlet
O Status Utama
P Vercel Link
Q Vercel Kata Sandi
R-X Jadwal Senin–Minggu
Y Jadwal Khusus
```

Import spreadsheet hanya dilakukan saat onboarding atau saat memang ingin memperbarui master data:

```bash
DATABASE_URL=postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster \
  PYTHONPATH=src uv run python scripts/import_sheet.py
```

Untuk perubahan operasional gunakan dashboard. Bot membaca PostgreSQL, memakai akun Shopee bersama `auto7313`, dan mempertahankan browser/session untuk berpindah antar `merchant_name` serta mengeksekusi target `store_id`.

## 5. Menghentikan dan menjalankan ulang

Di terminal aplikasi tekan:

```text
Ctrl+C
```

Kemudian jalankan ulang:

```bash
./scripts/dev.sh
```

## 6. Troubleshooting

Jika port `3001` sedang digunakan:

```bash
ss -ltnp | grep :3001
```

Hentikan proses lama, lalu jalankan `./scripts/dev.sh` kembali.

Jika data import kosong, cek URL CSV spreadsheet:

```bash
curl -I "$(grep GOOGLE_SHEETS_CSV_URL .env.example | cut -d= -f2-)"
```

Jika dependency belum tersedia, jalankan kembali:

```bash
uv sync
```
