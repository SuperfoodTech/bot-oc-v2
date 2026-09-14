# Definition of Done (DoD) - Sinkronisasi Nama Outlet Asli (Store Name) Shopee untuk Virtual Brand (VB)

Dokumen ini memuat kriteria keberhasilan (*Definition of Done*) untuk implementasi pengambilan nama outlet asli dari API Shopee Foody pada halaman *Business Hours* dan penyimpanannya ke database khusus untuk Virtual Brand (VB), serta visualisasinya di UI Admin Dashboard.

---

## 1. Scope & Batasan Pekerjaan
- [x] **Khusus Virtual Brand**: Fitur penyimpanan nama outlet asli dari Shopee hanya aktif untuk Virtual Brand (VB).
- [x] **Main-Bot Tidak Terpengaruh**: Bot O/C reguler (`main-bot`) tidak mengubah nama outlet yang sudah ada di database (`outlets.long_name`).
- [x] **Kepatuhan Paritas Worker**: File `main-vb/src/worker.py` dan `main-bot/src/worker.py` tetap identik secara persis (*byte-for-byte identical*).

---

## 2. Implementasi Teknis & Kode

### A. Shopee Client Layer (`store_status.py`)
- [x] Fungsi `get_actual_store_status` pada `src/shopee/store_status.py` dan `main-vb/src/shopee/store_status.py` mengekstrak `store_data.get("name")` dari respons `/api/seller/store`.
- [x] Return dictionary `get_actual_store_status` menyertakan key `"store_name"` dengan nilai string yang sudah di-`strip()` (atau string kosong jika tidak tersedia).

### B. Database Adapter Layer (`db.py`)
- [x] `main-vb/src/db.py`: Mengimplementasikan `update_outlet_name(store_id: str, store_name: str)` yang mengeksekusi:
  ```sql
  UPDATE outlets SET long_name = %s, updated_at = now()
  WHERE store_id = %s AND (long_name IS NULL OR long_name <> %s);
  ```
- [x] `src/backend/db.py`: Menyediakan fungsi stub `update_outlet_name(store_id: str, store_name: str)` berupa *no-op* (`pass`) agar kompatibel saat dipanggil worker tanpa mengubah data milik `main-bot`.

### C. Worker Engine Layer (`worker.py`)
- [x] Pada blok pengecekan `live_info` setelah `get_actual_store_status`, jika `live_info.get("store_name")` tersedia, worker memanggil `db.update_outlet_name(outlet.store_id, store_name)` dan memperbarui `outlet.nama_panjang_outlet`.
- [x] Dipastikan perintah `diff -u main-bot/src/worker.py main-vb/src/worker.py` menghasilkan *zero diff*.

### D. Frontend & UI Admin Dashboard (`admin_dashboard.html`)
- [x] Di tabel Virtual Brand (`.vb-store-table`), ditambahkan kolom mandiri `Nama Listing` untuk menampilkan nama asli outlet (`outlet.storeName`), berdampingan dengan kolom `Portal` (`outlet.portalName`).
- [x] Label kolom jam operasional tetap mematuhi aturan standar: `"Jam Hari Ini"`.
- [x] Tampilan responsif pada breakpoint desktop, tablet, dan mobile tetap rapi tanpa overflow tak terduga.

---

## 3. Pengujian & Verifikasi (Testing)

### A. Automated Testing
- [x] Unit test parser identitas toko Shopee (`tests/test_regular_hours_store_identity.py`) memverifikasi bahwa field `store_name` terekstraksi dengan tepat dan aman saat data kosong.
- [x] Unit test/verifikasi paritas memastikan `main-bot/src/worker.py` dan `main-vb/src/worker.py` 100% identik.
- [x] Test suite yang ada tetap lolos tanpa regresi.

### B. Manual / Live Verification
- [x] Saat patroli VB berjalan dan mengakses halaman Business Hours, log mencatat deteksi `store_name`.
- [x] Tabel `outlets` pada baris store VB terisi dengan nama asli dari Shopee (misal: `"Warung Lontong Sayur, WonderFood"` menggantikan fallback `"Lakubudi - 21897114"`).
- [x] Membuka halaman `/admin/dashboard?tab=vb` menampilkan nama asli toko pada baris outlet di dalam kartu brand yang di-*expand*.

---

## 4. Dokumentasi, Deployment, & Standar Operasional

- [x] **Dokumentasi Rilis**: Dibuat file rilis `update/1.13.8.md` yang memuat seksi `Whats New`, `Spesifikasi`, dan `Handling`.
- [x] **Pembaruan Aturan**: File `.agents/AGENTS.md` diperbarui mencatat versi `1.13.8` dan aturan terkait perilaku sinkronisasi nama outlet VB.
- [x] **Zero-Downtime Deployment**: Update backend/frontend diterapkan menggunakan perintah standar:
  ```bash
  docker compose build web
  docker compose up -d --no-deps web
  ```
  tanpa mematikan container `fm-bot`, `fm-vb`, atau `fm-postgres`.
