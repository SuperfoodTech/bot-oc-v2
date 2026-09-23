# Definition of Done (DoD) — Preemptive Cooperative On-Demand Execution & Instant Interrupt Engine

**Fitur**: Preemptive Cooperative Yielding, Instant Express Lane Preemption, Zero Order Leak  
**Modul**: `main-vb`, `main-bot`, `src/core`, `src/backend`  
**Target Versi**: Release 1.24.0  

Dokumen ini mendefinisikan kriteria kelayakan (*Acceptance Criteria*) dan standar kualitas (*Quality Gates*) yang wajib dipenuhi sebelum fitur ini dinyatakan selesai dan di-deploy ke produksi.

---

## 1. Kriteria Fungsional (*Functional Acceptance Criteria*)

### A. Preemptive Cooperative Yielding (< 1 Detik Interruption)
- [ ] **Instant Routine Patrol Interruption**: Ketika user mengubah toggle status brand di Dashboard Mitra atau Admin VB saat bot sedang berada di tengah-tengah pemindaian portal besar (misal outlet ke-5 dari 40 di *WonderFood*), loop patroli rutin **wajib langsung berhenti (*break / yield*) dalam waktu $\le \mathbf{1\text{ detik}}$**.
- [ ] **Preservation of Routine Queue**: Portal yang diinterupsi tidak boleh hilang atau ditandai selesai palsu (`not marked as completed in processed_keys`), dan wajib dapat dilanjutkan kembali setelah aksi express selesai.
- [ ] **Lightweight DB Check Overhead**: Pemeriksaan `has_pending_brand_actions()` di setiap awal loop outlet wajib berkecepatan tinggi ($\le 2\text{ms}$) dan tidak menambah beban CPU / database.

### B. On-Demand Express Lane Latency (< 3–5 Detik Total Execution)
- [ ] **Prioritas Mutlak P0**: Begitu patroli rutin terinterupsi, daemon wajib langsung mempromosikan status brand baru ke **Priority 100 (P0)** dan mengeksekusi `⚡ [EXPRESS LANE]` sebelum portal patroli rutin lainnya.
- [ ] **Targeted Store Execution**: Pemanggilan `worker.sync_all_stores(target_store_ids={...})` hanya memproses toko target dari brand yang di-toggle tanpa memindai toko lain.
- [ ] **Total End-to-End Latency**: Waktu total dari saat user menekan switch toggle di browser hingga aksi berhasil terverifikasi di Shopee Partner Web wajib $\le \mathbf{3\text{--}5\text{ detik}}$ (jika di portal yang sama) atau $\le \mathbf{8\text{--}12\text{ detik}}$ (jika memerlukan pergantian portal akun via `auto_switch_merchant`).

### C. Zero Order Leak & Compliance Guarding
- [ ] **Zero False Open (Pagar Jadwal)**: Bot dilarang keras membuka toko jika outlet berada di luar jam operasional reguler atau sedang dalam periode *Special Hours Close*, meskipun status toggle diminta ON.
- [ ] **Immediate Discord Notification**: Notifikasi Discord rekap aksi brand terkirim secara instan ($< 1\text{--}2$ detik) setelah target outlet selesai dieksekusi.

---

## 2. Kriteria Kualitas Kode & Integritas Arsitektur (*Technical Quality Gates*)

- [ ] **Byte-for-Byte Parity**: File `main-vb/src/worker.py` **WAJIB 100% identik *byte-for-byte*** dengan `main-bot/src/worker.py`. Perbedaan implementasi khusus VB hanya boleh diletakkan pada adapter `main-vb/src/db.py`.
- [ ] **Zero Memory Leak & Resource Reclamation**: Setiap siklus evaluasi daemon dan preemption event tetap memanggil `gc.collect()` dan `malloc_trim(0)` secara aman.
- [ ] **Safe Browser State**: Proses interupsi tidak boleh merusak context Selenium browser yang sedang aktif atau memicu invalid session id.
- [ ] **Fallback Resiliency**: Jika database mengalami temporary network glitch saat pengecekan preemption, worker tidak boleh crash dan wajib melanjutkan loop secara aman (*fail-safe*).

---

## 3. Kriteria Pengujian & Verifikasi (*Testing & Validation*)

- [ ] **Simulasi Patrol Interruption Test**:
  - Uji jalannya patroli portal 30+ outlet, kemudian masukkan request toggle brand di tengah jalan.
  - Verifikasi log mencatat `⚡ [ON-DEMAND PREEMPTION]` dan beralih ke Express Lane dalam $< 1$ detik.
- [ ] **End-to-End Verification Test**:
  - Uji pengubahan status dari dashboard (misal: brand *Katsu Geprek* atau lainnya).
  - Verifikasi perubahan langsung terefleksi di Shopee Partner Web dan status database dalam waktu $< 5$ detik.
- [ ] **Regression Test Suite**:
  - Seluruh unit test yang ada pada `tests/` lulus 100% (*ALL PASS*).

---

## 4. Kriteria Rilis & Deployment (*Release Compliance*)

- [ ] **Release Documentation**: Dokumentasi rilis dicatat lengkap di `update/1.24.0.md`.
- [ ] **Zero-Downtime Deployment**: Backend web dan bot di-deploy sesuai SOP tanpa mematikan sesi Selenium aktif.
