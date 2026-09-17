# Implementation Plan: In-Memory Operating Hours Skipping (Patrol Optimization)

**Dokumen**: Implementation Plan  
**Target Sistem**: `bot-oc` (Agency) & `bot-vb` (Virtual Brand)  
**Tujuan Utama**: 
1. Mengeliminasi navigasi browser / query XHR yang tidak perlu pada outlet yang sudah berada di luar jam operasional (toko tutup malam/subuh).
2. Memangkas waktu patroli malam/subuh dari $\approx 30$ detik menjadi $\le 2$ detik untuk ratusan toko yang sudah tutup.
3. Tetap mematuhi 100% SOP: Memastikan toko yang buka 24 jam atau yang jadwalnya belum valid tetap diperiksa secara presisi.

---

## 1. Analisis Masalah Saat Ini

Saat ini, pada siklus patroli rutin (*Patrol Lane*):
- `worker.py` tetap melakukan iterasi `for outlet in merchant_outlets:` dan memanggil `store_status.ensure_business_hours_page(driver, store_id=outlet.store_id)` untuk **setiap toko**.
- Di tengah malam (misal pukul 00:30 WIB), meskipun 180 dari 200 toko sudah tutup sejak pukul 22:00, bot tetap menavigasikan browser ke 180 halaman toko tersebut hanya untuk mendapati bahwa toko memang `CLOSED`.
- Hal ini menghabiskan CPU, memory browser, dan bandwidth server tanpa menghasilkan aksi apa pun.

---

## 2. Solusi: Fast In-Memory Pre-Patrol Filter (Skip Toko Tutup di RAM)

Sebelum melakukan navigasi browser Selenium atau memanggil API Shopee untuk sebuah outlet di dalam loop worker, bot melakukan evaluasi cepat di memori (RAM):

```text
                               ┌────────────────────────┐
                               │   Outlet dalam Loop    │
                               └───────────┬────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        │ Fast In-Memory Eligibility Filter   │
                        │ - Apakah jadwal sudah READY di DB?  │
                        │ - Apakah sekarang di luar jam buka? │
                        │ - Apakah DB status sudah CLOSED?    │
                        └──────────────────┬──────────────────┘
                                           │
                   ┌───────────────────────┴───────────────────────┐
                   ▼                                               ▼
     [Kondisi: Tutup Terjadwal & Sinkron]            [Kondisi: Butuh Navigasi Browser]
     - Di luar jam operasional                       - Sedang dalam jam buka (Live Watch)
     - DB status sudah CLOSED                        - Toko baru (Jadwal NOT_FETCHED_YET)
     - Tidak ada mismatch / toggle OFF               - Ada status mismatch di DB
                   │                                 - On-Demand Target (target_store_ids)
                   ▼                                               │
     ⚡ SKIP NAVIGASI BROWSER (0 ms)                                ▼
     - Append ke watched_outlets                    🌐 Navigasi Browser & Cek Status
     - Langsung lanjut ke toko berikutnya
```

---

## 3. Aturan Filter Kelayakan Navigasi Browser (*Navigation Eligibility Rules*)

Sebuah outlet **WAJIB di-skip dari navigasi browser** jika memenuhi SELURUH kriteria berikut:
1. `schedule_fetch_status in ('READY', 'FETCHED_EMPTY')` (Jadwal sudah valid tersimpan di database).
2. `not force_schedule_refresh` (Tidak sedang diminta refresh jadwal paksa).
3. `target_store_ids is None` atau toko tidak secara khusus ditargetkan.
4. `not is_within_operating_hours` (Waktu lokal saat ini berada di luar rentang jam buka hari ini).
5. Status terakhir di DB sudah `CLOSED` atau `PAUSE` (atau Vercel Toggle `OFF`).

Sebuah outlet **WAJIB diproses di browser** jika:
- Berada di dalam jam operasional hari ini (*Live Watchdog* untuk mendeteksi *random close* Shopee).
- Status jadwal masih `NOT_FETCHED_YET` atau `FETCH_RETRYING`.
- Status terakhir di DB tercatat `OPEN` padahal sekarang sudah jam tutup (butuh konfirmasi penutupan).
- Diminta secara on-demand via `target_store_ids`.

---

## 4. Rencana Tahapan Implementasi (Milestones)

### Milestone 1: Worker Pre-Patrol Filter
- [ ] Tambahkan helper `_should_inspect_store_in_browser(outlet, now_dt, ...)` pada `main-bot/src/worker.py` dan `main-vb/src/worker.py`.
- [ ] Terapkan guard condition sebelum pemanggilan `ensure_business_hours_page`.
- [ ] Jaga kesamaan *byte-for-byte* antara `main-bot/src/worker.py` dan `main-vb/src/worker.py`.

### Milestone 2: Unit Testing & Verification
- [ ] Buat unit test pada `tests/test_operating_hours_skipping.py` untuk menguji:
  - Toko di luar jam operasional di-skip dari navigasi browser.
  - Toko di dalam jam operasional tetap diperiksa di browser.
  - Toko baru tanpa jadwal tetap diperiksa di browser.
- [ ] Pastikan seluruh 76+ unit test lulus 100%.

### Milestone 3: Release Documentation & Versioning
- [ ] Catat rilis baru di `update/1.19.1.md`.
- [ ] Perbarui `.agents/AGENTS.md` dan `DoD.md`.
