# Definition of Done (DoD) - Virtual Brand Discord Notification Aggregation

**Fitur**: Atomic Group Notification Aggregation for Multi-Portal Virtual Brands  
**Modul**: `main-vb/src/db.py`, `main-vb/src/daemon.py`, `main-vb/src/core/notifier.py`  
**Target Release**: Release 1.22.2  

Dokumen ini mendefinisikan kriteria kelayakan (*Acceptance Criteria*) dan standar kualitas (*Quality Gates*) untuk perbaikan mekanisme pengiriman notifikasi Discord Virtual Brand agar tidak terkirim secara bertahap / mencicil per portal.

---

## 1. Kriteria Fungsional (Functional Acceptance Criteria)

### A. Atomic Per-Cycle Notification Delivery
- [ ] **Single Notification per Brand**: Setiap perubahan status Virtual Brand (Buka/Tutup) yang mencakup multi-portal hanya mengirimkan **1 notifikasi rekap ringkas** ke Discord setelah seluruh portal terkait selesai dieksekusi dalam siklus patroli.
- [ ] **Eliminasi Pesan Mencicil**: Tidak ada lagi pengiriman pesan intermediate bertahap (`Sebagian Berhasil`) yang dipicu oleh penyelesaian portal individual sebelum portal lainnya selesai diproses.
- [ ] **Zero Redundant Messages**: Brand yang tidak mengalami perubahan aksi atau tidak memiliki outlet yang dieksekusi pada siklus tersebut tidak memicu pengiriman webhook Discord.

### B. Akurasi Status Rekap (State Evaluation Parity)
- [ ] **Akurasi Rekap Tutup (Full Close)**: Jika seluruh outlet di bawah sebuah brand berhasil ditutup di seluruh portal, Discord menerima notifikasi `🔴 VB GROUP BERHASIL DITUTUP BOT` dengan daftar lengkap outlet berhasil.
- [ ] **Akurasi Rekap Buka (Full Open)**: Jika seluruh outlet di bawah sebuah brand berhasil dibuka di seluruh portal, Discord menerima notifikasi `🟢 VB GROUP BERHASIL DIBUKA BOT` dengan daftar lengkap outlet berhasil.
- [ ] **True Partial / Failure Alerts**: Status `🟠 SEBAGIAN BERHASIL` atau `🔴 GAGAL` hanya dikirimkan jika memang ada kegagalan eksekusi nyata pada API Shopee (misal error network/credential), bukan karena portal belum sempat dikunjungi.

---

## 2. Kriteria Kualitas Kode & Integritas Arsitektur (Technical Quality Gates)

- [ ] **Byte-for-Byte Parity Preserved**: File `main-vb/src/worker.py` **WAJIB tetap 100% identik byte-for-byte** dengan `main-bot/src/worker.py`. Logika agregasi dan trigger flush harus berada di adapter `main-vb/src/db.py` dan lifecycle runner `main-vb/src/daemon.py`.
- [ ] **Thread-Safe Queue Flush**: Pengelolaan buffer `_PENDING_BRAND_ACTIONS` di `main-vb/src/db.py` menggunakan `threading.Lock()` yang aman dari *race condition* antar worker/thread.
- [ ] **Headless & OOM Safe**: Eksekusi daemon tetap berjalan dengan `gc.collect()` deterministik dan konfigurasi browser `HEADLESS=true`.
- [ ] **Non-Interruption to Active Sessions**: Perubahan tidak boleh menghentikan container `fm-bot` atau merusak sesi aktif Selenium.

---

## 3. Kriteria Pengujian & Verifikasi (Testing & Validation)

- [ ] **Unit / Integration Tests**:
  - Test simulasi brand multi-portal (misal 3 portal berbeda): Memastikan `_flush_pending_brand_notifications` hanya dipanggil 1 kali di akhir siklus daemon dan menghasilkan 1 payload embed Discord yang valid.
  - Test simulasi brand single-portal: Memastikan perilaku tetap konsisten dan langsung terkirim utuh.
- [ ] **Dry-Run Validation**:
  - Menjalankan `python daemon.py --once --dry-run` pada service `main-vb` untuk memverifikasi transisi siklus dan flush berjalan bersih tanpa exception.

---

## 4. Kriteria Rilis & Dokumentasi (Release Compliance)

- [ ] **Dokumentasi Rilis**: Membuat file `update/1.22.2.md` yang mencantumkan `Whats New`, `Spesifikasi`, dan `Handling`.
- [ ] **Dokumentasi Aturan**: Memperbarui catatan di `AGENTS.md` terkait aturan siklus notifikasi Discord Virtual Brand.
