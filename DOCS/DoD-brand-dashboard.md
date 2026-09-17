# Definition of Done (DoD): Virtual Brand Dedicated Dashboard & Link Brand Column

## Kriteria Penyelesaian (Definition of Done)

1. **Kolom Link Brand di Admin Dashboard (`admin_dashboard.html`)**:
   - [ ] Kolom ke-6 tabel VB `.vb-store-table` berubah nama header dari `"Jadwal Khusus"` menjadi `"Link Brand"`.
   - [ ] Setiap baris outlet di bawah brand menampilkan tombol/link menuju `/brand/{slug}` yang dapat diklik atau disalin.

2. **Route Web & API Backend (`main.py` & `vb.py`)**:
   - [ ] Route `GET /brand/{slug}` merender halaman `brand_dashboard.html`.
   - [ ] Slug resolusi mendukung pencarian slug nama brand (misal: `bebek-carok`) maupun fallback ID brand.
   - [ ] API `GET /api/v1/brand/{slug}` mengembalikan detail brand, status live counts (`opened`, `failure`, `close`), jadwal operasional store pertama, daftar outlet 2 kolom, dan log aktivitas.
   - [ ] API `POST /api/v1/brand/{slug}/toggle` dapat memproses buka/tutup brand dan sinkron dengan database `vb_brands`.

3. **UI Dashboard Brand (`brand_dashboard.html`)**:
   - [ ] Akses langsung tanpa login page.
   - [ ] **Brand Hero Card**:
     - Menampilkan Nama Brand.
     - Menampilkan metric badges: Live Buka (Hijau), Perlu Cek (Kuning/Merah), Live Tutup (Abu-abu/Merah).
     - Menampilkan switch toggle 3-state tanpa label teks (Buka = Hijau, Tutup Manual = Merah, Luar Jadwal = Abu-abu disabled).
     - Tombol "Lihat Jadwal" membuka Bottom Sheet jadwal operasional 7 hari.
   - [ ] **Daftar Outlet Accordion**:
     - Header `Daftar Outlet (N Outlet)` dengan arrow down/up yang berotasi saat di-toggle.
     - Konten 2 kolom: Nama Outlet (Listing/Portal & Store ID) dan Status.
     - Tanpa tombol link ShopeeFood di dashboard brand.
   - [ ] **Bottom Sheet Jadwal Operasional**:
     - Menampilkan jadwal buka/tutup Senin–Minggu + Jadwal khusus (diambil dari store ID pertama).
   - [ ] **Riwayat Aktivitas**:
     - Menampilkan kartu aktivitas log audit terbaru brand.

4. **Kepatuhan Sistem & Deployment**:
   - [ ] Zero-downtime deployment: `docker compose build web && docker compose up -d --no-deps web`.
   - [ ] Service bot patroli `bot-oc.service` dan `bot-vb.service` tetap aktif berjalan tanpa terinterupsi.
   - [ ] Integritas *byte-for-byte* antara `main-bot/` dan `main-vb/` tetap terjaga (`PARITY_OK`).
   - [ ] Dokumentasi rilis `update/1.20.0.md` dan `.agents/AGENTS.md` diperbarui.
