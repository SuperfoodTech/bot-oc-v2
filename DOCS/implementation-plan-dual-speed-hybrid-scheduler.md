# Implementation Plan: Dual-Speed Hybrid Scheduler (On-Demand & Fast Patrol)

**Dokumen**: Implementation Plan  
**Target Sistem**: `bot-oc` (Agency) & `bot-vb` (Virtual Brand)  
**Tujuan Utama**: 
1. Menghilangkan latency eksekusi aksi buka/tutup toko saat skala outlet membesar (200+ outlet di 4 portal) dengan mekanisme **On-Demand Targeted Execution** (< 3–5 detik).
2. Memangkas durasi patroli keliling (*routine sweep*) dari **2–3 menit** menjadi **20–30 detik** melalui **Lightweight Live-State Fast Patrol**.
3. Tetap mematuhi 100% SOP & PRD (*Pagar Jadwal Operasional Shopee*) tanpa risiko *False Positive* atau *False Negative*.

---

## 1. Masalah Arsitektur Saat Ini

1. **Heavy Full-Sweep Serial**: Setiap kali portal diproses, bot memanggil 3 endpoint XHR/CDP untuk setiap toko (`get_regular_hours`, `get_special_hours`, dan `get_actual_store_status`). 200 outlet $\times$ 3 API = 600 request per siklus.
2. **Head-of-Line Blocking**: Jika sebuah toko di Portal 4 memerlukan aksi buka pada pukul 10:00:00, toko tersebut terblokir oleh inspeksi serial 150 toko di Portal 1, 2, dan 3.
3. **Tidak Ada Parameter Penargetan Outlet Spesifik**: Worker `sync_all_stores` hanya menerima `target_groups` (level portal), sehingga memproses seluruh toko di bawah portal tersebut meskipun hanya 1 toko yang butuh aksi.

---

## 2. Arsitektur Solusi: Dual-Speed Hybrid Engine

Arsitektur baru membagi operasi bot menjadi 2 jalur (*lanes*):

```text
                               ┌────────────────────────┐
                               │ PostgreSQL / Web State │
                               └───────────┬────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        │   In-Memory Scheduler Engine (RAM)  │
                        │   - Hitung Status & SOP Boundary    │
                        │   - Klasifikasi Prioritas P0 - P5   │
                        └──────────────────┬──────────────────┘
                                           │
                   ┌───────────────────────┴───────────────────────┐
                   ▼                                               ▼
     ⚡ EXPRESS LANE (P0 / P1)                       🚶 PATROL LANE (P3 / P4)
   - Trigger: Toggle Web, Mismatch, Boundary       - Trigger: Sistem Idle / Rutin
   - Dispatch: Targeted store_ids only             - Dispatch: Round-Robin Portal Sweep
   - API: Targeted XHR Action + Verify             - API: HANYA get_actual_store_status (1x)
   - Durasi: 3 - 5 detik                           - Durasi: 20 - 30 detik (200 toko)
                   │                                               │
                   └───────────────────────┬───────────────────────┘
                                           ▼
                               ┌────────────────────────┐
                               │   PostgreSQL Update    │
                               │   & SSE/Audit Log      │
                               └────────────────────────┘
```

---

## 3. Komponen dan Spesifikasi Teknis

### A. Modifikasi `worker.py` (`main-bot/src/worker.py` & `main-vb/src/worker.py`)
> **Catatan Aturan**: File `main-vb/src/worker.py` WAJIB 100% identik *byte-for-byte* dengan `main-bot/src/worker.py`.

1. **Parameter Baru pada `sync_all_stores`**:
   ```python
   def sync_all_stores(
       execute_actions: bool = True,
       default_interval_seconds: int = 60,
       target_groups: Optional[set] = None,
       target_store_ids: Optional[set[str]] = None,
       fetch_schedules_if_missing: bool = True,
   ) -> dict:
   ```
2. **Targeted Store Filtering**:
   - Jika `target_store_ids` diberikan, loop di dalam merchant group hanya memproses outlet yang ada di set tersebut:
     ```python
     if target_store_ids is not None and outlet.store_id not in target_store_ids:
         continue
     ```
3. **Pemisahan Heavy Schedule Fetch dari Routine Patrol**:
   - Jika toko **sudah memiliki** jadwal valid di database (`schedule_fetch_status in ('READY', 'FETCHED_EMPTY')` dan `outlet.shopee_regular_hours` ada), bot **TIDAK memanggil** `get_regular_hours` dan `get_special_hours` pada siklus patroli rutin.
   - Jadwal hanya ditarik jika:
     a. Status fetch masih `NOT_FETCHED_YET` atau `FETCH_RETRYING`.
     b. Di-trigger secara eksplisit via `force_schedule_refresh=True`.

---

### B. Modifikasi `scheduler.py` (`main-bot/src/scheduler.py` & `main-vb/src/scheduler.py`)

1. **Struktur Prioritas & Item Antrean**:
   - P0 (100 / 95): `ACTIONABLE_OPEN` / `ACTIONABLE_CLOSE` (Mismatch SOP / Web Toggle).
   - P1 (80 / 70): Boundary transisi jadwal ($\le 2$ menit sebelum buka/tutup) atau pause expiry.
   - P3 (40): Routine Live-State Heartbeat.
   - P4 (30): Toko baru yang butuh jadwal (`NOT_FETCHED_YET`).
   - P5 (10): Inactive / Suspended.
2. **Penyempurnaan `MerchantQueueItem`**:
   - Memastikan `due_store_ids` dan `actionable_store_ids` terpisah secara jelas agar daemon tahu apakah portal dipanggil untuk **Express Action** atau **Routine Patrol**.

---

### C. Modifikasi `daemon.py` (`main-vb/src/daemon.py` & `main-bot/src/daemon.py`)

1. **Prioritization Dispatch Logic**:
   - Saat ada antrean berstatus actionable (`item.actionable_count > 0`):
     - Panggil `worker.sync_all_stores(target_groups={item.merchant_key}, target_store_ids=set(item.due_store_ids))`.
     - Ini memastikan bot hanya mengeksekusi toko target tanpa me-loop seluruh isi portal.
2. **Opportunistic Portal Sweep**:
   - Setelah aksi Express selesai di portal tersebut, jika tidak ada aksi Express lain di portal lain, selesaikan pemeriksaan live status toko di portal aktif saat ini (*locality caching*).
3. **Dynamic Sleep & Instant Wake-Up**:
   - Saat semua toko sinkron, daemon tidur cerdas (15–30 detik).
   - Mendukung sinyal bangun instan jika ada event perubahan toggle dari dashboard web.

---

## 4. Rencana Tahapan Implementasi (Milestones)

### Milestone 1: Engine Worker Refactoring
- [ ] Tambahkan parameter `target_store_ids` pada `main-bot/src/worker.py` dan `main-vb/src/worker.py`.
- [ ] Optimalkan guard condition fetch jadwal: hanya fetch jika jadwal belum ada di DB.
- [ ] Verifikasi integritas byte-for-byte antar kedua file worker.

### Milestone 2: Scheduler & Queue Enhancement
- [ ] Perbarui `scheduler.py` untuk mengidentifikasi toko actionable vs toko heartbeat.
- [ ] Buat unit test untuk validasi prioritas antrean dan targeted due states.

### Milestone 3: Daemon Dispatch Loop Refactoring
- [ ] Modifikasi loop daemon di `main-vb/src/daemon.py` dan `main-bot/src/daemon.py`.
- [ ] Terapkan seleksi Express vs Patrol.
- [ ] Uji skenario switch portal on-demand.

### Milestone 4: End-to-End Verification & Benchmark
- [ ] Uji responsivitas toggle web dashboard (Target: latency < 5 detik).
- [ ] Uji durasi patroli 4 portal 200 toko (Target: total durasi < 30 detik).
- [ ] Uji ketahanan deteksi random close oleh Shopee.
- [ ] Buat dokumen rilis versi baru di `/update`.
