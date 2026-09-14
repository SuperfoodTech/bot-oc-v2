# Definition of Done (DoD) - Integrasi Fetch Special Hours Shopee & Penempatan UI (Agency Drawer & VB Kolom Baru)

Dokumen ini memuat kriteria keberhasilan (*Definition of Done*) untuk implementasi penarikan (*fetch*) jadwal khusus (*Special Hours*) dari API Shopee Foody (`/api/seller/store/special-hours`), migrasi penyimpanan database PostgreSQL `shopee_special_hours`, adapter database, integrasi worker engine bot-oc & bot-vb, serta penempatan informasi pada UI Dashboard Admin.

---

## 1. Scope & Batasan Pekerjaan
- [ ] **Dual Service Support**: Penarikan jadwal khusus Shopee aktif pada kedua engine: Bot O/C reguler (`main-bot`) dan Virtual Brand (`main-vb`).
- [ ] **Kepatuhan Paritas Worker**: File `main-bot/src/worker.py` dan `main-vb/src/worker.py` tetap identik secara persis (*byte-for-byte identical*, 0 diff).
- [ ] **Kepatuhan Paritas Browser**: File `src/core/browser.py` dan `main-vb/src/core/browser.py` tetap identik 100% (*byte-for-byte identical*).
- [ ] **Penempatan UI Terpisah Sesuai Arahan**:
  - **Tab Agency**: Informasi Jadwal Khusus diletakkan di dalam **Drawer Detail Outlet** (`.outlet-detail-panel`). Tabel utama Agency tetap bersih dengan 8 kolom standar.
  - **Tab Virtual Brand (VB)**: Informasi Jadwal Khusus ditampilkan pada tabel utama sebagai **kolom ke-6 di sebelah kanan kolom `Jam Hari Ini`** (`Jadwal Khusus`) pada `.vb-store-table`, serta di dalam drawer jadwal VB.

---

## 2. Implementasi Teknis & Kode

### A. Database Migration & Schema (`database/migrations/014_shopee_special_hours.sql`)
- [ ] Dibuat file migrasi `014_shopee_special_hours.sql` untuk menambahkan kolom `shopee_special_hours jsonb` pada tabel `outlet_states`.
- [ ] Versi migrasi dicatat ke tabel `schema_migrations`.
- [ ] Eksekusi migrasi berhasil dijalankan pada database PostgreSQL `fm-postgres`.

### B. Shopee Client Layer (`store_status.py`)
- [ ] Fungsi `get_special_hours(driver, store_id: str) -> Optional[Dict[str, Any]]` ditambahkan pada `src/shopee/store_status.py` dan `main-vb/src/shopee/store_status.py`.
- [ ] Endpoint: `GET https://foody.shopee.co.id/api/seller/store/special-hours` via XHR async script dengan timeout dan credential session Shopee.
- [ ] **Keamanan Identitas Toko (Store Identity Verification)**: Memvalidasi `data.store_id == requested_store_id`. Jika tidak cocok, melempar `StoreIdentityMismatch` dan tidak menyimpan data salah.
- [ ] Di-export pada `src/shopee/__init__.py` dan `main-vb/src/shopee/__init__.py`.

### C. Database Adapter Layer (`db.py`)
- [ ] `src/backend/db.py`: Mengimplementasikan `update_shopee_special_hours(store_id: str, special_hours: list) -> None` untuk menyimpan payload JSONB ke `outlet_states.shopee_special_hours`.
- [ ] `main-vb/src/db.py`: Mengimplementasikan fungsi `update_shopee_special_hours(store_id: str, special_hours: list) -> None` yang kompatibel.
- [ ] Query `list_outlets` dan endpoint `/api/v1/admin/vb/brands` menyertakan data `shopee_special_hours`.

### D. Worker Engine Layer (`worker.py`)
- [ ] Setelah memastikan halaman Business Hours tervalidasi, worker memanggil `store_status.get_special_hours(driver, store_id=outlet.store_id)`.
- [ ] Hasil list `special_hours` disimpan ke database via `db.update_shopee_special_hours`.
- [ ] Terverifikasi `cmp main-bot/src/worker.py main-vb/src/worker.py` menghasilkan *zero diff*.

### E. Frontend & UI Admin Dashboard (`admin_dashboard.html` & `styles.css`)
- [ ] **Agency Drawer (`openOutletDetail`)**: Menampilkan card/seksi "Jadwal Khusus Shopee" yang memuat rentang tanggal dan jam/status khusus jika ada (atau badge `"Tidak ada jadwal khusus"`).
- [ ] **Virtual Brand Table (`.vb-store-table`)**: Menambahkan kolom ke-6 `Jadwal Khusus` di sebelah kanan `Jam Hari Ini` dengan visualisasi ringkas rentang tanggal/jam khusus.
- [ ] **Virtual Brand Drawer (`vbScheduleDrawer`)**: Menampilkan rincian jadwal khusus di drawer samping VB.
- [ ] **Grid Styling**: Proporsi kolom tabel VB disesuaikan menjadi 6 kolom yang seimbang, rapat (*snug*), dan responsif.

---

## 3. Pengujian & Verifikasi (Testing)

### A. Automated Testing
- [ ] Dibuat unit test `tests/test_special_hours_store_identity.py` untuk menguji:
  - Sukses parsing respons `special_hours` dari Shopee.
  - Penolakan dan pelemparan exception `StoreIdentityMismatch` jika Store ID tidak cocok.
  - Penanganan respons kosong, null, atau timeout.
- [ ] Unit test UI layout contract memverifikasi keberadaan kolom `Jadwal Khusus` pada VB dan seksi jadwal khusus pada drawer Agency.
- [ ] Seluruh unit test suite (`uv run pytest tests/`) lulus 100% tanpa regresi.

### B. Paritas File
- [ ] `cmp main-bot/src/worker.py main-vb/src/worker.py` -> 0 diff.
- [ ] `cmp src/core/browser.py main-vb/src/core/browser.py` -> 0 diff.

---

## 4. Dokumentasi, Deployment & Standar Operasional

- [ ] **Dokumentasi Rilis**: Dibuat file rilis `update/1.14.0.md` yang memuat `Whats New`, `Spesifikasi`, dan `Handling`.
- [ ] **Pembaruan Aturan**: File `.agents/AGENTS.md` diperbarui dengan versi `1.14.0` dan aturan teknis fetch special-hours & penempatan UI.
- [ ] **Zero-Downtime Deployment**: Update backend web di-deploy dengan perintah standar:
  ```bash
  docker compose build web
  docker compose up -d --no-deps web
  ```
  tanpa menginterupsi bot atau database.
