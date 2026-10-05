# Implementation Plan & Definition of Done (DoD)

## 📌 Judul Rencana
**Deteksi Jadwal Khusus Buka (Special Hours Open), Penguncian Toggle Sesuai Kontrak, dan Normalisasi UX Writing Dashboard Mitra**

---

## 🎯 1. Objektif & Latar Belakang

1. **Deteksi Jadwal Khusus Buka (*Special Hours Open*)**:
   - Menjamin sistem bot dan backend mampu mengenali dan memproses Jadwal Khusus Shopee tipe **Buka** (`date_type != 1` atau memiliki `intervals` jam operasional tertentu), baik saat jadwal reguler mingguan terisi maupun saat jadwal reguler **kosong / dihapus merchant**.
   - Mencegah bot menghasilkan *Decision Error* / *"Jadwal reguler Shopee Sabtu tidak tersedia"* ketika toko buka berdasarkan Jadwal Khusus.

2. **Kepatuhan Kontrak Operasional Bot (*Contract Compliance*)**:
   - **Prinsip:** Bot **100% menghormati Jadwal Khusus Shopee** dan tidak mengintervensi atau mengubah status toko saat toko berada dalam periode Jadwal Khusus (baik Jadwal Khusus Tutup maupun Jadwal Khusus Buka).
   - **Perilaku Toggle:** Toggle pada antarmuka Dashboard Mitra (`/mitra/{slug}`) dan Admin Dashboard tetap **TERKUNCI / DISABLE OFF** (`state-closed` / switch abu-abu nonaktif di kiri).

3. **Standarisasi & Normalisasi UX Writing**:
   - **Saat Berada dalam Jadwal Khusus (Buka / Tutup):**
     - Pesan tunggal pada Hero Card Dashboard Mitra: **`'Bot tidak berfungsi karena terdapat Jadwal Khusus!'`**.
     - Tooltip & alert klik toggle: **`'Bot tidak berfungsi karena terdapat Jadwal Khusus!'`**.
     - Menghapus total pesan keliru `'Ada kesalahan data, harap hubungi Admin'`.
   - **Pada Drawer / Panel Jadwal ("Tampilkan jadwal"):**
     - Menampilkan rincian Jadwal Khusus (termasuk Jadwal Khusus Buka lengkap dengan rentang jam operasional WIB).
   - **Saat Toko Benar-benar Tidak Memiliki Jadwal (Reguler Kosong & Khusus Kosong / `FETCHED_EMPTY`):**
     - Teks summary jadwal hari ini: **`'Tidak memiliki jadwal operasional'`** (menggantikan `'Jadwal operasional belum tersedia'`).

---

## 🏗️ 2. Komponen yang Terdampak & Rencana Perubahan

### A. Engine Evaluasi Bot (`src/core/decision.py` & `main-vb/src/core/decision.py`)
- Pada fungsi `evaluate_outlet_status`:
  - Saat `active_special_hours` terdeteksi:
    - Jika `not is_open_special` (Jadwal Khusus Tutup / di luar jam buka khusus): Menetapkan `target=TARGET_CLOSE` dan `reason="Tutup berdasarkan Jadwal Khusus Shopee ([Deskripsi])"`.
    - Jika `is_open_special` (Jadwal Khusus Buka): Menetapkan `action=ACTION_NO_CHANGE` dan `reason="Mengikuti Jadwal Khusus Shopee ([Deskripsi])"`.
  - Memastikan evaluasi langsung selesai (*return*) pada tahap Jadwal Khusus tanpa jatuh ke pengecekan `require_regular_schedule` yang memicu false log *"Jadwal reguler Shopee [Hari] tidak tersedia"*.

### B. State Derivation & DB Runtime (`src/backend/db.py` & `main-vb/src/backend/db.py`)
- Pada fungsi `derive_outlet_runtime_state`:
  - Saat `active_special_hours` aktif:
    - `display_toggle_disabled = True` (selalu terkunci nonaktif).
    - `display_toggle_on = False` (toggle off di kiri).
    - `display_toggle_reason = 'SPECIAL_HOURS'`.
    - `bot_phase = 'WAITING_SCHEDULE'` / `'SPECIAL_HOURS'`.
    - `display_note = 'Bot tidak berfungsi karena terdapat Jadwal Khusus!'`.
  - Saat `schedule_fetch_status == 'FETCHED_EMPTY'` dan tidak ada special hours:
    - Menghapus label error, menstandarkan keterangan menjadi *"Tidak memiliki jadwal operasional"*.

### C. Antarmuka Dashboard Mitra & Admin (`src/backend/templates/user_dashboard.html` & `admin_dashboard.html`)
- **`getOutletStateContext(outlet)`**:
  - Jika `hasSpecialHours == true` (baik buka maupun tutup), secara deterministik menyetel:
    - `toggleDisabled = true`
    - `toggleChecked = false`
    - `toggleReason = 'SPECIAL_HOURS'`
    - `isSpecialHoursClosed = true` (mengunci toggle agar tidak bisa diubah).
- **`getMitraScheduleMetaText(outlet, stateContext)` & `formatTodayScheduleSummary`**:
  - Jika `hasSpecialHours == true`: mengembalikan `'Bot tidak berfungsi karena terdapat Jadwal Khusus!'`.
  - Jika `FETCHED_EMPTY`: mengembalikan `'Tidak memiliki jadwal operasional'`.
  - Menghilangkan cabang teks `'Ada kesalahan data, harap hubungi Admin'`.
- **`renderOutletSchedule(outlet)`**:
  - Memastikan fungsi rendering *Special Hours* memformat dan menampilkan entri Jadwal Khusus Buka dengan interval jam (`HH:mm - HH:mm WIB`) secara jelas di panel drawer jadwal.

---

## ⏰ 4. Dynamic Past Time Picker Restriction (1:1 Reproducibility Across All Portals)

1. [x] **Mitra Agency Dashboard (`user_dashboard.html`)**: Opsi jam lampau dan menit lampau pada hari ini di-disable secara otomatis, opsi menit otomatis menyesuaikan saat jam dipilih, dan semua opsi aktif saat memilih tanggal masa depan.
2. [x] **Admin Console Agency Modal (`admin_dashboard.html`)**: 1:1 perilaku identik untuk modal custom duration pause Agency.
3. [x] **Admin Console Virtual Brand Modal (`admin_dashboard.html`)**: 1:1 perilaku identik untuk modal custom duration pause VB Brand.
4. [x] **Mitra Virtual Brand Dashboard (`brand_dashboard.html`)**: 1:1 perilaku identik untuk modal custom duration pause Mitra Brand (`/brand/{slug}`).
5. [x] **Zero-Downtime Deployment Verified**: Service web berhasil di-rebuild dan dijalankan tanpa interupsi pada bot daemon (`v1.32.0`).
