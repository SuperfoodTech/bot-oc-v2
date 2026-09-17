# Implementation Plan: Virtual Brand Dedicated Dashboard & Link Brand Column

## 1. Overview
Fitur ini menyediakan **Dashboard Khusus Per-Brand Virtual Brand (VB)** yang dapat diakses langsung tanpa form login via direct slug URL (`/brand/{slug}`), serta menggantikan kolom "Jadwal Khusus" pada tabel outlet VB di Admin Dashboard menjadi kolom **"Link Brand"**.

---

## 2. Arsitektur & Spesifikasi Detail

### A. Kolom Link Brand pada Admin Dashboard (`admin_dashboard.html`)
- Menggantikan header dan isi kolom ke-6 "Jadwal Khusus" pada `.vb-store-table` menjadi **"Link Brand"**.
- Menampilkan tautan/tombol langsung ke `/brand/${brand.slug}` dengan icon link dan opsi buka dashboard brand di tab baru.

### B. Route & API Backend (`src/backend/main.py` & `src/backend/vb.py`)
- **Route Halaman**: `GET /brand/{slug}` $\rightarrow$ merender `brand_dashboard.html`.
- **API Data Brand**: `GET /api/v1/brand/{slug}` (Public):
  - Mengembalikan metadata brand (`id`, `name`, `slug`, `applied_status`, `requested_status`, `pause_until`, `is_schedule_locked`).
  - Menghitung agregat status count: `opened` (Live Buka), `failure` (Perlu Cek), `close` (Live Tutup).
  - Mengambil data jadwal operasional 7 hari & jadwal khusus dari Store ID pertama yang valid di brand tersebut.
  - Mengembalikan daftar outlet (2 kolom: Nama Outlet/Portal/Store ID dan Status).
  - Mengembalikan 10 riwayat log audit aktivitas terakhir untuk brand tersebut.
- **API Toggle Brand**: `POST /api/v1/brand/{slug}/toggle` (Public/Direct):
  - Memperbarui status toggle brand (`applied_status` / `requested_status`) di database PostgreSQL `vb_brands`.
  - Memicu Express Lane worker bot patroli untuk eksekusi on-demand.

### C. Desain & Komponen Dashboard Brand (`brand_dashboard.html` & `styles.css`)
1. **Brand Hero Card**:
   - **Nama Brand** (Judul utama).
   - **Metrik Status Badges**:
     - `Live Buka: X` (badge hijau)
     - `Perlu Cek: Y` (badge kuning/merah)
     - `Live Tutup: Z` (badge abu-abu/merah)
   - **Switch Toggle Brand 3-State**:
     - Buka/Aktif: Hijau (`state-open`, knob kanan).
     - Tutup Manual: Merah (`state-paused`, knob kiri).
     - Luar Jadwal: Abu-abu terkunci (`state-closed`, knob kiri, disabled).
     - Tanpa label teks di samping toggle.
   - **Tombol "Lihat Jadwal"**: Membuka Bottom Sheet jadwal operasional.

2. **Daftar Outlet (Collapsible Accordion dengan Arrow `▼` / `▲`)**:
   - Header tombol: `Daftar Outlet (N Outlet)` dengan icon panah transisi rotasi halus.
   - Konten 2 kolom:
     - **Kolom 1: Nama Outlet** (Nama listing, Portal, dan Store ID).
     - **Kolom 2: Status** (Status live Shopee / badge status).

3. **Bottom Sheet Jadwal Operasional**:
   - Modal drawer yang meluncur dari bawah layar saat tombol "Lihat Jadwal" diklik.
   - Menampilkan jam buka/tutup Senin–Minggu + Jadwal khusus (jika ada).
   - Tombol tutup / klik backdrop untuk menutup.

4. **Riwayat Aktivitas Terakhir**:
   - Menampilkan log aktivitas audit pembukaan/penutupan bot pada outlet brand tersebut.

---

## 3. Langkah Eksekusi

1. **Backend Route & Controller (`src/backend/main.py` & `src/backend/vb.py`)**:
   - Tambahkan fungsi helper pencarian brand by slug / ID di `vb.py`.
   - Tambahkan route `GET /brand/{slug}`, `GET /api/v1/brand/{slug}`, dan `POST /api/v1/brand/{slug}/toggle`.
2. **Template Dashboard Brand (`src/backend/templates/brand_dashboard.html`)**:
   - Buat template mandiri berdesain responsif, clean, dengan Hero Card, Accordion 2-kolom, Bottom Sheet Jadwal, dan Log Aktivitas.
3. **Styling CSS (`src/backend/static/css/styles.css`)**:
   - Tambahkan styling pendukung untuk bottom sheet jadwal brand dan accordion outlet 2 kolom.
4. **Update Admin Dashboard (`src/backend/templates/admin_dashboard.html`)**:
   - Ganti kolom ke-6 "Jadwal Khusus" pada tabel VB menjadi "Link Brand".
5. **Zero-Downtime Deployment & Pengujian**:
   - Build dan up container `web` dengan `docker compose build web && docker compose up -d --no-deps web`.
   - Jalankan automated tests dan verifikasi endpoint.
6. **Dokumentasi Rilis**:
   - Buat `update/1.20.0.md` (karena penambahan fitur/route baru) dan perbarui `AGENTS.md`.
