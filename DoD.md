# Definition of Done (DoD) - Immediate Brand-Completion Notification Delivery

**Fitur**: Pengiriman Notifikasi Discord Instan Saat Seluruh Outlet Brand Selesai Dieksekusi  
**Modul**: `main-vb/src/db.py`, `main-vb/src/daemon.py`, `tests/`  
**Target Release**: Release 1.23.6  

Dokumen ini menetapkan kriteria kelayakan (*Acceptance Criteria*) dan standar kualitas (*Quality Gates*) sebelum fitur pengiriman notifikasi instan berbasis penyelesaian eksekusi brand (*Brand-Completion Immediate Flush*) dinyatakan selesai (*Done*).

---

## 1. Kriteria Fungsional (Functional Acceptance Criteria)

### A. Immediate Brand-Level Notification Dispatch
- [ ] **Instant Delivery on Completion**: Begitu seluruh outlet yang menjadi target aksi dari sebuah brand selesai dieksekusi (di seluruh portal yang bersangkutan), notifikasi Discord untuk brand tersebut dikirimkan secara instan (< 1–2 detik) tanpa harus menunggu seluruh siklus patroli keliling (*Cycle*) selesai.
- [ ] **Zero Fragmentation (No Partial/Mencicil per Portal)**: Untuk brand multi-portal, notifikasi tetap ditahan (*hold*) sampai portal terakhir yang memuat outlet brand tersebut selesai diproses, sehingga Discord tetap hanya menerima **1 pesan rekap ringkas per brand**.
- [ ] **Comprehensive Outcome Support**:
  - Full Success (🟢 BUKA / 🔴 TUTUP): Dikirim instan saat seluruh outlet sukses.
  - Partial Success (🟠 SEBAGIAN): Dikirim instan saat seluruh target outlet telah dicoba dan sebagian gagal.
  - All Failed (🔴 GAGAL): Dikirim instan saat seluruh target outlet telah dicoba dan semua gagal.
  - Auto-Guarding (🟢/🔴/🟠 TARGETED): Dikirim instan saat aksi pemulihan outlet selesai.

### B. Fallback & Safety Net
- [ ] **End-of-Cycle Safety Sweep**: Di akhir siklus daemon (`while RUNNING:` loop selesai), `db.flush_pending_brand_notifications()` tetap dipanggil sebagai jaring pengaman (*safety net*) untuk memastikan tidak ada pesan pending yang tertinggal.
- [ ] **Targeted Brand Flush Support**: Fungsi `db.flush_pending_brand_notifications(brand_ids=...)` mendukung pembersihan selektif hanya untuk brand yang telah selesai, menjaga buffer brand lain yang masih memiliki sisa antrean.

---

## 2. Kriteria Kualitas Kode & Integritas Arsitektur (Technical Quality Gates)

- [ ] **Worker Byte-for-Byte Parity**: File `main-vb/src/worker.py` **WAJIB tetap 100% identik byte-for-byte** dengan `main-bot/src/worker.py`. Logika orchestrasi murni berada di `main-vb/src/daemon.py` dan `main-vb/src/db.py`.
- [ ] **Thread-Safe Queue Manipulation**: Manipulasi buffer `_PENDING_BRAND_ACTIONS` dan `_BRAND_TOGGLED_IDS` aman dari *race conditions* menggunakan `_PENDING_LOCK`.
- [ ] **Non-Interruption / Zero Downtime**: Tidak ada penghentian container `fm-bot` atau interupsi session browser di `bot-vb`.

---

## 3. Kriteria Pengujian & Verifikasi (Testing & Validation)

- [ ] **Unit Tests**:
  - Pengujian `flush_pending_brand_notifications(brand_ids=...)` hanya mengirim dan menghapus brand yang ditargetkan.
  - Pengujian simulasi multi-portal: Portal 1 selesai -> buffer ditahan -> Portal 2 selesai -> notifikasi ter-flush seketika.
  - Test suite pada `tests/test_vb_notification_flush.py` lulus 100%.
- [ ] **Regression Suite**: Seluruh test suite (55+ tests) lulus tanpa regresi.

---

## 4. Kriteria Rilis & Dokumentasi (Release Compliance)

- [ ] **Dokumentasi Rilis**: Membuat file update `update/1.23.6.md` yang memuat `Whats New`, `Spesifikasi`, dan `Handling`.
- [ ] **Pencatatan Versi di AGENTS.md**: Memperbarui nomor rilis terbaru dan poin aturan di `.agents/AGENTS.md`.
