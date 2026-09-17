# Definition of Done (DoD) - In-Memory Operating Hours Skipping

**Fitur**: Fast In-Memory Pre-Patrol Filter (Skip Navigasi Browser untuk Toko Tutup Terjadwal)  
**Modul**: `main-bot`, `main-vb`, `src/core`  
**Status Baseline**: Release 1.19.0  

Dokumen ini mendefinisikan kriteria kelayakan (*Acceptance Criteria*) dan standar kualitas (*Quality Gates*) sebelum optimasi pelewatan (*skipping*) toko di luar jam operasional dinyatakan selesai.

---

## 1. Kriteria Fungsional (Functional Acceptance Criteria)

### A. Pelewatan Cerdas di Memori (In-Memory Skip)
- [ ] **Zero Browser Navigation for Inactive Stores**: Outlet yang sudah berada di luar jam operasional dengan status DB `CLOSED` dan jadwal `READY` tidak memicu navigasi browser (`ensure_business_hours_page`) ataupun panggilan API XHR Shopee.
- [ ] **Durasi Patroli Jam Malam**: Durasi siklus keliling saat sebagian besar toko tutup (misal tengah malam) turun menjadi $\le \mathbf{2 - 4 \text{ detik}}$ untuk seluruh portal.
- [ ] **Immediate Watched Outlet Aggregation**: Outlet yang di-skip tetap dimasukkan ke dalam `watched_outlets` untuk perhitungan `next_wake_hint_seconds` (waktu bangun saat jam buka toko berikutnya tiba).

### B. Preservasi Live Watchdog & Kasus Khusus
- [ ] **Active Hours Inspection**: Outlet yang berada di dalam jam operasional tetap diperiksa secara live di browser untuk mendeteksi penutupan sepihak (*random close*) oleh Shopee.
- [ ] **New Store Discovery**: Outlet dengan status `NOT_FETCHED_YET` atau `FETCH_RETRYING` tetap diproses di browser untuk mengambil data jadwal awal.
- [ ] **Mismatch Resolution**: Outlet yang di DB tercatat `OPEN` tetapi sekarang sudah masuk jam tutup tetap diperiksa di browser untuk memastikan penutupan telah terjadi.
- [ ] **On-Demand Exemption**: Pemanggilan eksplisit via `target_store_ids` atau `force_schedule_refresh=True` mengabaikan filter pelewatan ini.

---

## 2. Kriteria Kualitas Kode & Integritas Arsitektur (Technical Quality Gates)

- [ ] **Byte-for-Byte Parity**: File `main-vb/src/worker.py` WAJIB 100% identik *byte-for-byte* dengan `main-bot/src/worker.py`.
- [ ] **Zero False Positive / Negative**: Keputusan pembukaan dan penutupan toko tetap 100% patuh pada SOP `evaluate_outlet_status`.
- [ ] **Zero Memory Leak**: `gc.collect()` tetap dijalankan di setiap akhir iterasi daemon.

---

## 3. Kriteria Pengujian & Verifikasi (Testing & Validation)

- [ ] **Unit Tests**: Test baru pada `tests/test_operating_hours_skipping.py` lulus 100%.
- [ ] **Regression Suite**: Seluruh test suite (76+ test) lulus tanpa regresi.

---

## 4. Kriteria Rilis & Dokumentasi (Release Compliance)

- [ ] **Dokumentasi Rilis**: File rilis baru dibuat di `update/1.19.1.md`.
- [ ] **Aturan Project**: Aturan dicatat di `.agents/AGENTS.md`.
