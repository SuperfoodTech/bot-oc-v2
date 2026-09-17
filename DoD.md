# Definition of Done (DoD) - Virtual Brand Notification Direction & Status Evaluation Fix

**Fitur**: Perbaikan Penentuan Arah & Evaluasi Notifikasi Discord Virtual Brand (Brand Toggle & Guarding)  
**Modul**: `main-vb/src/db.py`, `tests/test_vb_notification_flush.py`  
**Target Release**: Release 1.23.8  

Dokumen ini menetapkan kriteria kelayakan (*Acceptance Criteria*) dan standar kualitas (*Quality Gates*) sebelum perbaikan logika evaluasi arah notifikasi Discord Virtual Brand dinyatakan selesai (*Done*).

---

## 1. Kriteria Fungsional (Functional Acceptance Criteria)

### A. Deterministic Notification Direction Evaluation
- [ ] **Strict Status-Driven Evaluation for Brand Toggle**:
  - Pada mode Brand Toggle (`is_brand_toggle == True`), penentuan jenis aksi (`summary_action` dan `is_open`) **100% dipandu oleh `applied_status` brand** (`applied_status == "ON"` -> `ACTION_OPEN` / DIBUKA; `applied_status == "PAUSED"` -> `ACTION_CLOSE` / DITUTUP).
  - Menghilangkan logika `any(a in ("ACTION_OPEN", ...) for a in actions_types)` yang rentan terhadap kontaminasi sisa aksi patroli lama.
- [ ] **Majority/Executed Action Evaluation for Auto-Guarding**:
  - Pada mode Auto-Guarding (`is_brand_toggle == False`), arah aksi ditentukan berdasarkan dominasi aksi pemulihan aktual yang dieksekusi (`open_count >= close_count`), dengan fallback ke `applied_status`.
- [ ] **Stale Buffer Purging on Status Apply**:
  - Saat status toggle baru diaplikasikan pada brand di `apply_all_pending_statuses`, buffer `_PENDING_BRAND_ACTIONS[brand_id]` dibersihkan dari aksi lama sebelum eksekusi dimulai agar tidak ada sisa catatan aksi sebelumnya.

### B. Accurate Success & Failure Categorization
- [ ] **Brand Toggle Close**: Jika brand di-pause/tutup (`applied_status == 'PAUSED'`), seluruh outlet yang berhasil di-pause (`live_st in ('PAUSE', 'CLOSED', 'OFF')`) tanpa kegagalan tercatat masuk ke kategori **Berhasil Ditutup**, bukan Gagal Dibuka.
- [ ] **Brand Toggle Open**: Jika brand di-buka (`applied_status == 'ON'`), seluruh outlet yang aktif (`live_st in ('ON', 'OPEN')`) masuk ke kategori **Berhasil Dibuka**.

---

## 2. Kriteria Kualitas Kode & Integritas Arsitektur (Technical Quality Gates)

- [ ] **Worker Byte-for-Byte Parity**: File `main-vb/src/worker.py` **WAJIB tetap 100% identik byte-for-byte** dengan `main-bot/src/worker.py`. Seluruh penyesuaian hanya berada di adapter `main-vb/src/db.py`.
- [ ] **Thread-Safe Buffer Operations**: Seluruh manipulasi buffer `_PENDING_BRAND_ACTIONS` dan `_BRAND_TOGGLED_IDS` terlindungi mutex `_PENDING_LOCK`.
- [ ] **Zero Downtime**: Penyesuaian adapter di `main-vb/src/db.py` tidak menginterupsi jalannya daemon patroli.

---

## 3. Kriteria Pengujian & Verifikasi (Testing & Validation)

- [ ] **Unit Tests**:
  - Test case untuk skenario replikasi issue: Brand di-toggle PAUSED saat buffer memiliki sisa `ACTION_OPEN` dari patroli sebelumnya, memastikan notifikasi dikirim sebagai `ACTION_CLOSE` dengan status SUKSES.
  - Test case untuk Brand di-toggle ON.
  - Test case untuk Auto-Guarding mode (Open & Close).
  - Test suite pada `tests/test_vb_notification_flush.py` lulus 100%.
- [ ] **Full Regression**: Seluruh unit test suite lulus tanpa error/regresi.

---

## 4. Kriteria Rilis & Dokumentasi (Release Compliance)

- [ ] **Dokumentasi Rilis**: Membuat file update `update/1.23.8.md` yang memuat ringkasan issue, akar masalah, perbaikan logika, dan spesifikasi penanganan.
- [ ] **Pencatatan Versi di AGENTS.md & UPDATES.md**: Memperbarui nomor rilis terbaru (`1.23.8`) dan mencatat aturan determinasi arah notifikasi pada `.agents/AGENTS.md` dan `UPDATES.md`.
