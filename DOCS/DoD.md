# Definition of Done (DoD) - Dual-Speed Hybrid Scheduler

**Fitur**: On-Demand Targeted Execution & Lightweight Fast Patrol Engine  
**Modul**: `main-bot`, `main-vb`, `src/core`, `src/backend`  
**Status Baseline**: Release 1.18.5  

Dokumen ini mendefinisikan kriteria kelayakan (*Acceptance Criteria*) dan standar kualitas (*Quality Gates*) yang wajib dipenuhi sebelum implementasi ini dinyatakan selesai dan siap dirilis ke produksi.

---

## 1. Kriteria Fungsional (Functional Acceptance Criteria)

### A. On-Demand & Targeted Execution (Express Lane)
- [ ] **Targeted Store Filtering**: Pemanggilan `worker.sync_all_stores(target_store_ids={...})` hanya memproses toko yang terdaftar di dalam set, dan melewatkan (*skip total*) pembacaan XHR untuk toko lain di portal yang sama.
- [ ] **Latency Eksekusi On-Demand**: Dari saat toggle brand/outlet diubah di Dashboard Web hingga aksi sukses dieksekusi di Shopee, waktu total $\le \mathbf{5 \text{ detik}}$ (termasuk jeda switch portal jika diperlukan).
- [ ] **Preemptive Interrupt**: Toko dengan prioritas P0 (mismatch / toggle berubah) dapat menyela antrean patroli rutin tanpa harus menunggu seluruh toko di portal sebelumnya selesai dipindai.
- [ ] **Opportunistic Resumption**: Setelah selesai mengeksekusi on-demand di sebuah portal, bot tidak melakukan switch bolak-balik yang sia-sia (*no redundant ping-pong switches*).

### B. Lightweight Fast Patrol (Patrol Lane)
- [ ] **Pemisahan API Call Statis vs Dinamis**: Patroli rutin hanya memanggil `get_actual_store_status` (1 API call) untuk toko yang jadwalnya sudah ada di database.
- [ ] **Durasi Patroli 4 Portal**: Durasi 1 putaran penuh patroli rutin untuk $\ge 200$ outlet di 4 portal selesai dalam waktu $\le \mathbf{30 \text{ detik}}$ (turun drastis dari sebelumnya 2–3 menit).
- [ ] **Deteksi Penutupan Sepihak (*Random Close*)**: Jika Shopee menutup toko sepihak di jam operasional saat toggle ON, bot mendeteksinya pada putaran patroli dan otomatis menaikkan prioritasnya ke P0 untuk membuka toko kembali.

### C. Kepatuhan SOP & Pagar Jadwal
- [ ] **Zero False Positive**: Bot **dilarang keras** membuka toko di luar jam operasional Shopee meskipun toggle brand berstatus ON.
- [ ] **Zero False Negative**: Bot **wajib** mengoreksi dan membuka toko jika toko tertutup/pause di jam operasional saat toggle ON.
- [ ] **Initial Schedule Fetch**: Toko baru yang belum memiliki data jadwal (`NOT_FETCHED_YET` atau `FETCH_RETRYING`) tetap ditarik jadwal reguler & jadwal khususnya secara lengkap sebelum dievaluasi.

---

## 2. Kriteria Kualitas Kode & Integritas Arsitektur (Technical Quality Gates)

- [ ] **Byte-for-Byte Parity**: File [`main-vb/src/worker.py`](file:///root/bot-oc-v2-prod/main-vb/src/worker.py) WAJIB 100% identik *byte-for-byte* dengan [`main-bot/src/worker.py`](file:///root/bot-oc-v2-prod/main-bot/src/worker.py). Perbedaan VB hanya boleh berada di adapter [`main-vb/src/db.py`](file:///root/bot-oc-v2-prod/main-vb/src/db.py).
- [ ] **Zero Memory Leak / OOM Prevention**: Setiap iterasi loop daemon wajib menjalankan `gc.collect()` di dalam blok `finally:`.
- [ ] **Single Instance & Headless Compliance**: Service `fm-bot-vb` wajib tetap beroperasi dalam mode `HEADLESS=true` di server.
- [ ] **Error Handling & Quarantine**: Error pada satu outlet atau saat identity mismatch (`StoreIdentityMismatch`) tidak boleh menghentikan daemon atau memengaruhi evaluasi outlet lainnya.

---

## 3. Kriteria Pengujian & Verifikasi (Testing & Validation)

- [ ] **Unit Tests**:
  - Seluruh unit test pada `tests/` lulus 100% tanpa regresi.
  - Test baru untuk validasi `target_store_ids` di worker dan prioritas di scheduler lulus.
- [ ] **Integration Test**:
  - Simulasi switch antar 4 portal dengan kombinasi status (P0, P1, P3) berjalan mulus.
- [ ] **Live Dry-Run**:
  - Uji daemon dengan flag `--once` dan continuous loop menghasilkan log terstruktur yang bersih tanpa unhandled exceptions.

---

## 4. Kriteria Rilis & Dokumentasi (Release Compliance)

- [ ] **Dokumentasi Rilis**: File rilis baru dibuat di direktori `update/<SEMVER>.md` (misal `update/1.19.0.md`) dengan seksi lengkap: `Whats New`, `Spesifikasi`, dan `Handling`.
- [ ] **Aturan Project**: Aturan baru terkait arsitektur scheduler dan targeted execution dicatat di [`AGENTS.md`](file:///root/bot-oc-v2-prod/.agents/AGENTS.md).
- [ ] **Zero-Downtime Deployment**: Perubahan diverifikasi dapat di-deploy tanpa mengganggu session Selenium yang sedang aktif jika tidak ada schema breaking change.
