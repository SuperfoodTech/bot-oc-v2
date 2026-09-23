# Implementation Plan: Preemptive Cooperative On-Demand Execution & Instant Interrupt Engine

**Dokumen**: Implementation Plan  
**Target Sistem**: `bot-oc` (Agency) & `bot-vb` (Virtual Brand), `src/core`, `src/backend`  
**Tujuan Utama**:
1. Menjamin aksi *On-Demand* (Buka / Tutup / Pause Brand di Dashboard) selalu dieksekusi secara **instan (< 3–5 detik)** di Shopee Partner Web tanpa pernah tertahan oleh antrean patroli rutin.
2. Mengeliminasi *Blocking Window* pada portal besar (30–50 outlet per akun) dengan menerapkan mekanisme **Preemptive Cooperative Yielding** di dalam loop worker Selenium.
3. Mencegah kebocoran pesanan masuk (*Zero Order Leak*) akibat jeda tunggu penutupan toko saat jam sibuk atau jeda buka saat pergantian status operasional.

---

## 1. Analisis Akar Masalah (Root Cause)

1. **Sequential Worker Blocking**:
   * Pada portal besar (seperti *WonderFood* atau *Gurame Bakar, Do Eat*), satu siklus patroli rutin `[PATROL LANE]` memakan waktu **2.5 – 4 menit** karena memeriksa puluhan outlet secara sekuensial.
   * `worker.sync_all_stores()` berjalan secara synchronous dan tidak pernah memeriksa perubahan status DB di tengah-tengah loop.
2. **Late State Pickup**:
   * Fungsi `apply_all_pending_statuses()` hanya dipanggil saat daemon berada di luar worker (sebelum masuk ke portal berikutnya).
   * Jika user mengubah toggle saat bot sedang di outlet ke-5 dari 40 outlet, permintaan tersebut tertahan di database hingga outlet ke-40 selesai diperiksa.
3. **Queue Re-sorting Delay**:
   * Jika portal yang sedang disapu baru saja selesai, status toggle baru yang baru di-apply harus bersaing dengan portal lain yang sudah mengantre di memory queue jika tidak ada preemption prioritas mutlak.

---

## 2. Arsitektur Solusi: Preemptive Cooperative Yielding Engine

```text
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                      User Klik Toggle di Dashboard Web                      │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │  PostgreSQL UPDATE vb_brands              │
                  │  (requested_status = 'ON' / 'PAUSED')     │
                  └─────────────────────┬─────────────────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        ▼                               ▼
        ┌──────────────────────────────┐ ┌──────────────────────────────┐
        │  Kondisi 1: Bot Sedang Tidur │ │  Kondisi 2: Bot Sedang Sweep │
        │  (Idle Sleep / Waiting)      │ │  (Patrol Lane 40 Outlets)    │
        └───────────────┬──────────────┘ └──────────────┬───────────────┘
                        │                               │
                        │                               ▼
                        │                ┌──────────────────────────────┐
                        │                │ worker.py Check per-Outlet:  │
                        │                │ has_pending_brand_toggle()?  │
                        │                └──────────────┬───────────────┘
                        │                               │ (TRUE)
                        │                               ▼
                        │                ⚡ [PREEMPTION TRIGGERED]
                        │                - Abort patrol loop (< 1 detik)
                        │                - Yield control ke daemon.py
                        │                               │
                        └───────────────┬───────────────┘
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │ daemon.py: apply_all_pending_statuses()   │
                  │ - Promosikan Brand ke Priority 100 (P0)   │
                  └─────────────────────┬─────────────────────┘
                                        │
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │ ⚡ [EXPRESS LANE] Dispatch Target Outlets  │
                  │ - worker.sync_all_stores(target_store_ids)│
                  │ - Switch Merchant + XHR Toggle Shopee     │
                  │ - Durasi Total: < 3 - 5 Detik             │
                  └─────────────────────┬─────────────────────┘
                                        │
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │ ✅ Toko Sukses Terbuka/Tertutup di Shopee  │
                  │ - Kirim Notifikasi Discord                │
                  │ - Lanjutkan sisa patroli rutin yang tunda │
                  └───────────────────────────────────────────┘
```

---

## 3. Rincian Modifikasi Teknis

### A. Modifikasi Modul Database Adapter (`main-vb/src/db.py` & `src/backend/db.py`)
1. **Lightweight Preemption Check Function**:
   Menyediakan fungsi pengecekan super cepat ($< 1\text{ms}$) tanpa overhead:
   ```python
   def has_pending_brand_actions() -> bool:
       """Check if there are pending requested_status changes waiting to be applied."""
       with connection() as conn:
           row = conn.execute(
               "SELECT 1 FROM vb_brands WHERE is_active=true AND requested_status IS NOT NULL LIMIT 1"
           ).fetchone()
           return bool(row)
   ```
2. **Instant State Transition Helper**:
   Memastikan pemanggilan `apply_all_pending_statuses(conn)` mengembalikan daftar `brand_id` yang ter-update sehingga daemon langsung mengetahui portal target mana yang wajib di-prioritaskan.

---

### B. Modifikasi Worker Engine (`main-vb/src/worker.py` & `main-bot/src/worker.py`)
> **Aturan Wajib**: `main-vb/src/worker.py` dan `main-bot/src/worker.py` **WAJIB 100% identik *byte-for-byte***.

1. **Preemptive Yielding Check di Loop Outlet**:
   Di dalam `sync_all_stores()`, sebelum memproses setiap `outlet` dalam `merchant_outlets`:
   ```python
   # Hanya berlaku saat menjalankan PATROL LANE (target_store_ids is None)
   if target_store_ids is None and hasattr(db, "has_pending_brand_actions"):
       if db.has_pending_brand_actions():
           log.info(
               f"⚡ [ON-DEMAND PREEMPTION] Urgent user toggle detected in DB! "
               f"Yielding routine patrol lane for '{portal_name}' to execute Express Lane immediately..."
           )
           yielded_for_preemption = True
           break
   ```
2. **Return Value Flag**:
   Menyertakan `"yielded_for_preemption": True` pada dictionary hasil `sync_all_stores` agar daemon tidak menandai portal tersebut sebagai selesai (`processed_keys.add`).

---

### C. Modifikasi Scheduler & Daemon Engine (`main-vb/src/daemon.py` & `main-bot/src/daemon.py`)
1. **Preemption Handling & Fast-Path Re-Queue**:
   Jika worker menghasilkan `yielded_for_preemption == True`:
   - Jangan masukkan `selected.merchant_key` ke `processed_keys`.
   - Segera panggil `db.fetch_merchant_outlets_from_db()` untuk meng-apply status baru ke memory.
   - P0 Express Lane langsung terpilih pada iterasi berikutnya ($< 100\text{ms}$).
2. **Inter-Service Control API Trigger**:
   Pada `bot_api.py`, endpoint `/api/v1/trigger_action` mendukung sinyal *instant wake up* yang menginterupsi `time.sleep` daemon jika bot sedang berada di fase jeda antar-siklus.

---

### D. Modifikasi Backend Web API (`src/backend/vb.py` & `src/backend/main.py`)
1. **Instant Wakeup Dispatch**:
   Saat endpoint `request_status` berhasil melakukan update ke tabel `vb_brands`:
   - Backend memicu request asinkron non-blocking ke `http://127.0.0.1:8082/api/v1/trigger_action` (atau IPC file/event trigger).
   - Menjamin bot langsung tersadar detik itu juga tanpa menunggu siklus polling.

---

## 4. Urutan Langkah Pengerjaan (Step-by-Step Execution Plan)

1. **Step 1 — Modul Database**:
   Implementasikan `has_pending_brand_actions` di `main-vb/src/db.py` dan `main-bot/src/db.py`.
2. **Step 2 — Worker Preemption Engine**:
   Pasang pengecekan cooperative yielding di `main-vb/src/worker.py` dan sinkronkan 1:1 ke `main-bot/src/worker.py`.
3. **Step 3 — Daemon Scheduling Fast-Path**:
   Perbarui `main-vb/src/daemon.py` agar menangani `yielded_for_preemption` dan mendahulukan Express Lane P0 secara deterministik.
4. **Step 4 — Testing & Verifikasi**:
   - Jalankan unit tests / integration tests.
   - Uji simulasi toggle saat bot sedang di tengah patroli portal besar.
   - Verifikasi latensi aksi berubah dari ~5 menit menjadi $< 3\text{--}5$ detik.
5. **Step 5 — Dokumentasi & Release Note**:
   Buat catatan rilis di `update/1.24.0.md` dan perbarui `AGENTS.md`.
