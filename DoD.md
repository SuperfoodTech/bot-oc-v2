# Definition of Done (DoD) — Virtual Brand (VB) Sheet Migration & Strict Ingestion Gate

Dokumen ini mendefinisikan kriteria penyelesaian (*Definition of Done*) untuk implementasi migrasi spreadsheet Virtual Brand (VB) ke format relasional 4-kolom (`Owner`, `Outlet`, `Portal`, `Store ID`), normalisasi nama portal (`DoEat` $\rightarrow$ `Gurame Bakar, Do Eat`), serta aturan validasi data ketat sebelum disimpan ke database untuk dieksekusi bot.

---

## 1. Kriteria Penerimaan (*Acceptance Criteria*)

### A. Format & Parsing Spreadsheet Baru
- [ ] **URL Spreadsheet Terhubung**: Menggunakan endpoint resmi Google Sheets CSV Virtual Brand aktif `gid=935753758`.
- [ ] **Struktur 4-Kolom Terpetakan Sempurna**:
  - Kolom 1: `Owner` (Nama pemilik asli, misal: *A Isyah, Amir, Dina, Mahrudin, dll.*).
  - Kolom 2: `Outlet` (Nama Virtual Brand, misal: *Ayam Geprek Suroboyo Ampel, Baru Rasa, Katsunami, dll.*).
  - Kolom 3: `Portal` (Nama merchant portal, misal: *SuperFood, WonderFood, LOKARASA, DoEat*).
  - Kolom 4: `Store ID` (ID toko numerik ShopeeFood, misal: *21758641, 22299093, dll.*).
- [ ] **Backward / Fallback Compatibility**: Parser memiliki deteksi cerdas yang mampu mengenali format relasional 4-kolom maupun matrix lama secara adaptif tanpa crash.

### B. Portal Aliasing & Normalization
- [ ] **Mapping Otomatis DoEat**: Nilai `"DoEat"`, `"do eat"`, `"doeat"`, maupun `"Gurame Bakar, Do Eat"` secara deterministik dinormalisasi menjadi nama resmi Shopee Partner:
  $$\textbf{"Gurame Bakar, Do Eat"}$$
- [ ] **Normalisasi Portal Lainnya**:
  - `"superfood"` / `"SuperFood"` $\rightarrow$ `"SuperFood"`
  - `"wonderfood"` / `"WonderFood"` $\rightarrow$ `"WonderFood"`
  - `"lokarasa"` / `"LOKARASA"` $\rightarrow$ `"LOKARASA"`

### C. Validasi Ketat (*Strict Data Ingestion Gate*)
- [ ] **Validasi Store ID**:
  - Wajib terisi dan berupa angka digit murni (`store_id.strip().isdigit()`).
  - Baris dengan Store ID kosong, bernilai teks seperti `"-", "#N/A", "undefined"`, atau non-digit **dilarang masuk ke database** dan otomatis di-skip.
- [ ] **Validasi Portal**:
  - Wajib terisi dan valid.
  - Baris dengan kolom portal kosong **dilarang masuk ke database** dan otomatis di-skip.
- [ ] **Validasi Brand**:
  - Wajib memiliki nama brand/outlet yang jelas. Baris kosong diabaikan.
- [ ] **Proteksi Bot Execution**:
  - Dashboard Admin, Dashboard Mitra VB, dan Bot Daemon (`fm-bot-vb`) hanya membaca data yang tersimpan valid di tabel database (`outlets` & `vb_brand_outlets`). Toko yang tidak valid tidak akan pernah dimuat atau dieksekusi oleh bot.

---

## 2. Kriteria Kualitas & Integritas Data

- [ ] **Idempotensi Import**: Menjalankan import berkali-kali menghasilkan data yang konsisten (tidak membuat duplikasi data toko, brand, atau relasi).
- [ ] **Pembersihan Stale Brands**: Brand yang sudah tidak ada di spreadsheet aktif otomatis dinonaktifkan (`is_active = false`) agar tidak membebani siklus patroli bot.
- [ ] **Pencatatan Audit Log**: Setiap aktivitas import sheet mencatat detail ringkasan ke `admin_audit_logs` (jumlah brand, outlet dibuat, outlet di-link, baris di-skip).

---

## 3. Kriteria Verifikasi & Pengujian (*Testing Criteria*)

- [ ] **Unit / Local Script Test**:
  - Pengujian live fetch terhadap CSV `gid=935753758` sukses memproses 113 outlet valid dari 29 brand dan 22 owner.
  - Pengujian baris invalid (mock data tanpa store ID / tanpa portal) terbukti 100% di-skip.
  - Test suite `pytest` pada modul worker dan backend berjalan hijau (*PASS*).
- [ ] **Zero-Downtime Deployment**:
  - Update service backend web dieksekusi dengan perintah:
    ```bash
    docker compose build web && docker compose up -d --no-deps web
    ```
  - Sesi bot Selenium (`fm-bot` & `fm-bot-vb`) tetap berjalan aktif 24/7 tanpa interupsi.
