# Implementation Plan: Merchant-Aware Scheduler

Status: implemented in `main-bot/src/scheduler.py`, `main-bot/src/daemon.py`, and `main-bot/src/worker.py`.

The first phase now dispatches one merchant group at a time, refreshes runtime
state after each dispatch, and drains currently due groups by priority. The
legacy full-sync worker remains available for manual `/bot/sync` compatibility.

Dokumen ini menjelaskan rencana implementasi `merchant-aware scheduler` untuk bot-oc berdasarkan codebase saat ini.

Fokus utamanya:
- menurunkan latency penjagaan outlet,
- mengurangi biaya switch merchant,
- menjaga mismatch penting agar tidak terlambat lebih dari target operasional,
- tanpa membuang `decision engine` dan `worker` yang sekarang sudah relatif stabil.

## 1. Tujuan Praktis

Target operasional yang ingin dicapai:
- toleransi delay normal: `1-5 menit`
- worst acceptable delay: jangan menembus `10 menit` dalam kondisi single-instance sehat

Target ini terutama untuk kasus:
- outlet ditutup random oleh Shopee saat seharusnya buka,
- pause aktif yang harus dijaga saat sesi reguler berikutnya mulai,
- outlet yang baru gagal post-action verification,
- banyak merchant dengan biaya switch context yang mahal.

## 2. Masalah di Arsitektur Sekarang

Saat ini bot masih berbasis `global cycle`:
1. daemon membangunkan worker
2. worker mengambil semua outlet
3. worker mengelompokkan outlet per `(username, portal)`
4. worker memproses semua group secara serial
5. daemon tidur lagi

Perbaikan yang sudah ada:
- intra-cycle grouping per merchant sudah mengurangi biaya switch
- pause boundary yang terlewat di tengah cycle bisa memicu wake-up cepat sesudah cycle selesai

Tetapi bottleneck utamanya masih ada:
- merchant penting tetap bisa menunggu karena urutan global
- outlet yang sudah dipatrol lebih awal bisa stale saat cycle masih berlanjut
- banyak merchant dengan priority berbeda masih diperlakukan hampir sama
- random close Shopee tetap menunggu giliran cycle berikutnya

Kesimpulannya:
- problem utama sekarang bukan lagi di `decision rule`
- problem utamanya ada di `siapa yang dipatrol duluan` dan `kapan merchant itu dipanggil lagi`

## 3. Prinsip Desain

Scheduler baru akan memakai prinsip berikut:

1. Unit eksekusi utama adalah `merchant group`
   - kunci group: `(username, portal_name)`
   - alasan: switch merchant mahal, sementara multi-outlet dalam merchant yang sama relatif murah

2. Unit pembentuk prioritas tetap `outlet`
   - karena urgency muncul dari kondisi outlet
   - tetapi saat dieksekusi, urgency itu digabung ke merchant group

3. Scheduler harus `event-driven by due time`, bukan hanya `fixed interval`
   - setiap outlet punya `next_check_at`
   - merchant group mengambil `min(next_check_at)` dari outlet-outletnya

4. Scheduler harus `priority-aware`
   - mismatch kritis diproses dulu
   - schedule boundary penting diproses sebelum heartbeat biasa

5. Scheduler harus `recompute often`
   - idealnya setelah satu merchant selesai dipatrol, scheduler hitung ulang
   - bukan menunggu satu global cycle penuh

6. Worker yang ada tetap dipertahankan
   - `decision engine`, action open/pause, session recovery, dan post-verification tidak dibuang
   - yang diubah adalah lapisan penentuan urutan patroli

## 4. Scope dan Non-Goal

### Scope fase pertama
- mengganti loop global menjadi `merchant-aware scheduling`
- memproses merchant group satu per satu berdasarkan prioritas dan due time
- menghitung `next_check_at` per outlet secara in-memory
- tetap single-instance

### Non-goal fase pertama
- distributed scheduler lintas banyak instance
- webhook real-time dari Shopee
- rewrite total worker
- persistence penuh metadata scheduler ke database

## 5. Gambaran Arsitektur Baru

Arsitektur yang direkomendasikan:

```text
Daemon Loop
  -> load current runtime outlets from DB
  -> build scheduler snapshot
  -> pick next merchant group
  -> worker sync only that merchant group
  -> refresh DB/runtime snapshot
  -> pick next merchant group again
  -> sleep only when no group is due
```

Perubahan mindset penting:
- sekarang bukan lagi `sekali bangun -> proses semua merchant`
- tetapi `sekali bangun -> pilih merchant paling penting -> proses -> hitung ulang`

Ini adalah cara termurah untuk mendekati SLA 1-5 menit tanpa rewrite total.

## 6. Konsep Data Scheduler

Rekomendasi fase pertama adalah membuat modul baru, misalnya:
- `main-bot/src/scheduler.py`

Modul ini akan bekerja di memory dan tidak butuh migrasi DB pada fase awal.

### Struktur outlet due

```python
@dataclass
class OutletDueState:
    store_id: str
    merchant_key: tuple[str, str]
    due_at: datetime
    priority: int
    reason: str
    desired_state: str
    live_state: str
    bot_phase: str
    within_schedule: bool
    actionable: bool
```

### Struktur merchant queue item

```python
@dataclass
class MerchantQueueItem:
    merchant_key: tuple[str, str]
    username: str
    portal_name: str
    due_at: datetime
    priority: int
    due_store_ids: list[str]
    actionable_count: int
    reasons: list[str]
```

### Arti field penting
- `due_at`: kapan outlet atau merchant itu wajib dipatrol lagi
- `priority`: tingkat urgensi
- `actionable`: apakah saat dipatrol kemungkinan besar akan ada aksi atau verifikasi penting
- `due_store_ids`: outlet pemicu merchant group tersebut

## 7. Aturan Prioritas yang Direkomendasikan

Rekomendasi priority sederhana untuk fase pertama:

| Priority | Nama | Contoh kondisi | Target perilaku |
|---|---|---|---|
| `P0 = 100` | Actionable mismatch | desired `OPEN`, live `CLOSED/PAUSE`, masih dalam jadwal | Proses secepat mungkin |
| `P0 = 95` | Actionable close mismatch | desired `PAUSE` atau `MANUAL_OFF`, live `OPEN` | Proses secepat mungkin |
| `P0 = 90` | Post-action verify pending | action baru dikirim, verify gagal/mismatch | Recheck cepat |
| `P1 = 80` | Pause boundary | pause aktif, sesi reguler berikutnya akan mulai sebelum `pause_until` | Patrol dekat boundary |
| `P1 = 70` | Pause expiry | `pause_until` segera berakhir | Buka kembali tepat waktu |
| `P2 = 60` | Waiting next schedule open | desired `OPEN`, sekarang di luar jadwal | Bangun di jadwal buka berikutnya |
| `P3 = 40` | In-sync open heartbeat | outlet sedang buka normal | Patrol berkala |
| `P4 = 30` | Schedule unavailable | jadwal Shopee belum berhasil dibaca | Coba lagi berkala |
| `P5 = 10` | Closed inactive states | suspended atau manual off yang sudah sinkron | Patrol jarang |

## 8. Aturan `next_check_at` Per Outlet

Ini inti scheduler. Setiap outlet harus diberi due time.

### 8.1 Desired `OPEN`, live `CLOSED/PAUSE`, within schedule

Kondisi:
- outlet seharusnya buka
- tapi live state belum sesuai

Aturan:
- `due_at = now`
- `priority = P0`

Alasan:
- ini kasus layanan inti penjagaan outlet

### 8.2 Desired `PAUSE` atau `MANUAL_OFF`, live `OPEN`

Kondisi:
- outlet seharusnya tidak melayani order
- tapi Shopee masih membuka outlet

Aturan:
- `due_at = now`
- `priority = P0`

### 8.3 Post-action verify pending atau mismatch

Kondisi:
- action open/pause sudah dikirim
- verify belum berhasil atau hasilnya belum cocok

Aturan:
- `due_at = now + 15s`
- `priority = P0`

Catatan:
- ini melanjutkan pola yang sudah ada di worker saat ini

### 8.4 Pause aktif, sekarang sedang break antar jadwal, ada sesi reguler lagi sebelum `pause_until`

Kondisi:
- outlet sedang pause
- Shopee sedang tutup normal karena break
- tetapi nanti ada sesi reguler berikutnya sebelum pause habis

Aturan:
- `due_at = next_regular_schedule_start`
- `priority = P1`

### 8.5 Pause aktif, tidak ada sesi reguler lagi sebelum `pause_until`

Aturan:
- `due_at = pause_until`
- `priority = P1`

### 8.6 Desired `OPEN`, sekarang di luar jadwal

Aturan:
- `due_at = next_regular_schedule_start`
- `priority = P2`

### 8.7 Outlet `OPEN` dan sinkron normal

Aturan:
- `due_at = now + OPEN_HEARTBEAT_SECONDS`
- `priority = P3`

Rekomendasi awal:
- `OPEN_HEARTBEAT_SECONDS = 180`

### 8.8 Schedule unavailable

Aturan:
- `due_at = now + SCHEDULE_RETRY_SECONDS`
- `priority = P4`

Rekomendasi awal:
- `SCHEDULE_RETRY_SECONDS = 180`

### 8.9 Suspended atau manual off yang sudah sinkron

Aturan:
- `due_at = now + INACTIVE_HEARTBEAT_SECONDS`
- `priority = P5`

Rekomendasi awal:
- `INACTIVE_HEARTBEAT_SECONDS = 600`

## 9. Agregasi dari Outlet ke Merchant Group

Setelah semua outlet punya `due_at` dan `priority`, scheduler melakukan agregasi:

1. group outlet berdasarkan `(username, portal_name)`
2. untuk tiap merchant group, ambil:
   - `group_due_at = min(outlet.due_at)`
   - `group_priority = max(outlet.priority)`
   - `due_store_ids = semua outlet yang memicu due_at/priority tinggi`
   - `actionable_count = jumlah outlet actionable`

### Kenapa agregasi ini penting
Karena yang mahal adalah:
- login account
- switch merchant
- validasi page context

Sedangkan sesudah merchant context benar:
- memproses outlet ke-2, ke-3, ke-4 dalam merchant yang sama jauh lebih murah

## 10. Aturan Pemilihan Merchant Berikutnya

Rekomendasi urutan sort:
1. `priority` tertinggi dulu
2. `due_at` paling awal dulu
3. `actionable_count` terbesar dulu
4. prefer merchant yang sama dengan current warm context bila tie
5. fallback lexical `(username, portal_name)` agar stabil

### Kenapa `actionable_count` berguna
Jika dua merchant sama-sama due sekarang, merchant yang punya lebih banyak outlet actionable biasanya memberi nilai bisnis lebih besar per sekali switch.

### Kenapa sticky merchant hanya tie-break
Karena kita tidak ingin hemat switch merchant mengalahkan mismatch kritis di merchant lain.

## 11. Bentuk Loop Daemon Baru

Rekomendasi perubahan utama di daemon:

### Loop lama
```text
while running:
  sync_all_stores()
  sleep(interval)
```

### Loop baru
```text
while running:
  outlets = load_outlets_from_db()
  snapshot = build_scheduler_snapshot(outlets, now)
  next_group = pick_next_due_group(snapshot, now)

  if next_group exists:
      sync_only_this_group(next_group)
      continue

  sleep_until(snapshot.earliest_due_at or fallback_heartbeat)
```

### Dampak praktis
- kalau masih ada backlog merchant due sekarang, daemon tidak tidur default interval
- daemon akan terus mengambil merchant penting berikutnya
- sleep hanya terjadi kalau memang tidak ada merchant yang harus diprioritaskan sekarang

## 12. Refactor yang Dibutuhkan di Worker

Worker sekarang sudah punya blok proses per merchant group. Itu bisa dimanfaatkan.

Rekomendasi refactor minimum:

1. Ekstrak logika satu merchant group ke helper khusus
   - contoh nama: `sync_merchant_group(username, portal_name, merchant_outlets, execute_actions=True)`

2. Pertahankan helper lama:
   - session recovery
   - business hours validation
   - regular hours sync
   - live status fetch
   - decision evaluation
   - action execution
   - post-action verification

3. Ubah `sync_all_stores()` menjadi wrapper kompatibilitas
   - fungsi lama tetap bisa dipakai untuk full patrol fallback
   - tetapi daemon baru lebih sering memakai `sync_selected_groups()` atau `sync_next_group()`

4. Keluarkan informasi post-action recheck ke hasil worker
   - agar scheduler bisa menjadikannya `P0`

## 13. Modul Baru yang Disarankan

### `main-bot/src/scheduler.py`

Fungsi yang direkomendasikan:
- `build_outlet_due_state(outlet, now_dt) -> OutletDueState`
- `build_scheduler_snapshot(outlets, now_dt) -> list[MerchantQueueItem]`
- `pick_next_due_group(snapshot, now_dt, current_context=None) -> MerchantQueueItem | None`
- `compute_sleep_seconds(snapshot, now_dt, default_interval_seconds) -> int`

### Fungsi helper tambahan yang mungkin perlu
- `get_next_outlet_due_at(...)`
- `get_next_regular_schedule_start(...)`
- `is_actionable_mismatch(...)`

Sebagian helper ini bisa diletakkan di:
- `src/core/decision.py`, jika masih domain logic murni
- atau `scheduler.py`, jika khusus untuk policy scheduling

## 14. Rencana Implementasi Bertahap

### Fase 1. Extract and Stabilize

Tujuan:
- pisahkan logika worker per merchant group

Langkah:
1. ekstrak kode `for (username, portal_name), merchant_outlets in grouped_outlets.items()` menjadi helper reusable
2. pastikan helper bisa dipanggil hanya untuk satu merchant group
3. pertahankan `sync_all_stores()` agar kompatibel

Output:
- worker siap dipakai oleh scheduler baru tanpa rewrite besar

### Fase 2. In-Memory Merchant-Aware Scheduler

Tujuan:
- daemon tidak lagi menjalankan global full cycle sebagai jalur utama

Langkah:
1. buat `scheduler.py`
2. load outlet dari DB
3. hitung `desired/live/bot_phase` yang ada sekarang
4. hitung `next_check_at` dan `priority` per outlet
5. agregasikan ke merchant group
6. pilih merchant group paling due
7. panggil worker hanya untuk merchant itu
8. selesai merchant itu, recompute snapshot

Output:
- scheduling utama menjadi merchant-aware
- delay tail akan turun signifikan

### Fase 3. Fast Backlog Drain

Tujuan:
- jika banyak merchant due bersamaan, backlog tetap cepat habis

Langkah:
1. selama masih ada merchant dengan `due_at <= now`, daemon jangan tidur
2. proses merchant satu per satu
3. recompute setelah tiap merchant

Output:
- boundary bersamaan tidak lagi menunggu global cycle selesai

### Fase 4. Observability

Tujuan:
- admin bisa melihat kenapa merchant tertentu diprioritaskan

Langkah:
1. expose scheduler snapshot ringkas ke log atau endpoint admin internal
2. tampilkan:
   - merchant key
   - next due
   - priority
   - due reason
   - due outlet ids

Output:
- debugging dan tuning scheduler lebih mudah

### Fase 5. Optional Persistence

Tujuan:
- jika nanti dibutuhkan recovery state yang lebih kuat

Pilihan:
- tambah kolom atau tabel runtime untuk:
  - `next_check_at`
  - `last_patrolled_at`
  - `scheduler_priority`
  - `scheduler_reason`

Catatan:
- ini tidak wajib untuk fase pertama

## 15. Acceptance Criteria

Scheduler baru dianggap berhasil jika memenuhi hal berikut:

1. Merchant group dengan mismatch `desired OPEN` vs `live CLOSED/PAUSE` selalu didahulukan di atas heartbeat normal.
2. Merchant dengan boundary penting tidak menunggu global cycle penuh untuk dikunjungi lagi.
3. Jika banyak merchant due bersamaan, daemon memproses backlog tanpa tidur interval default di antaranya.
4. Jumlah switch merchant per aksi penting turun dibanding full global cycle lama.
5. Dalam single-instance sehat, mismatch kritis normalnya terkoreksi dalam `<= 5 menit`.
6. Tail delay `> 10 menit` menjadi kasus langka dan hanya terjadi saat:
   - browser/session recovery gagal berat
   - jaringan bermasalah
   - Shopee lambat atau error

## 16. Test Plan

### Unit test scheduler
- outlet `PENDING_OPEN` harus menghasilkan `due_at = now`
- outlet `PENDING_PAUSE` harus menghasilkan `due_at = now`
- pause aktif saat break harus menghasilkan `due_at = next schedule start`
- outlet di luar jadwal dengan desired `OPEN` harus menghasilkan `due_at = next schedule start`
- outlet in-sync open harus menghasilkan heartbeat biasa

### Unit test agregasi merchant
- dua outlet satu merchant, satu due sekarang dan satu due nanti:
  - merchant group harus due sekarang
- tiga merchant due sekarang:
  - urutan harus mengikuti priority lalu due time

### Integration test worker + scheduler
- daemon memproses satu merchant group dulu, bukan semua merchant
- setelah merchant pertama selesai, snapshot dihitung ulang
- backlog due-now diproses tanpa sleep default

### Scenario test yang penting
- random close pada outlet aktif
- multi-schedule pause melewati break
- tiga merchant punya boundary yang sama
- satu merchant punya banyak outlet actionable dan merchant lain punya satu outlet heartbeat biasa

## 17. Risiko dan Tradeoff

### Kelebihan
- cocok dengan biaya switch merchant yang mahal
- lebih dekat ke SLA penjagaan outlet
- tidak membuang decision logic yang sudah ada
- rollout bisa bertahap

### Tradeoff
- loop daemon jadi lebih sering recompute snapshot
- struktur worker perlu dipecah lebih modular
- observability awal harus cukup baik agar tuning prioritas tidak membingungkan

### Risiko implementasi
- jika due rule terlalu agresif, daemon bisa terlalu sering bangun
- jika sticky merchant terlalu kuat, mismatch merchant lain bisa terlambat
- jika priority tidak jelas, debugging perilaku scheduler akan sulit

## 18. Rekomendasi Implementasi Minimum

Kalau ingin versi paling minimal namun bernilai tinggi, aku rekomendasikan:

1. ekstrak `sync_merchant_group(...)` dari worker sekarang
2. buat `scheduler.py` in-memory
3. ubah daemon menjadi:
   - pilih satu merchant due
   - proses
   - recompute
   - tidur hanya jika tidak ada merchant due
4. gunakan priority dasar:
   - actionable mismatch
   - post-action verify pending
   - pause boundary
   - next schedule open
   - open heartbeat
   - inactive heartbeat

Dengan empat langkah itu saja, kita sudah berpindah dari:
- `cycle global yang dioptimalkan`

menjadi:
- `scheduler merchant-aware minimal yang production-relevant`

## 19. Urutan File yang Akan Disentuh Nanti

Kalau plan ini dieksekusi, file yang kemungkinan disentuh adalah:
- `main-bot/src/worker.py`
- `main-bot/src/daemon.py`
- `main-bot/src/scheduler.py` baru
- `src/core/decision.py`
- `tests/` untuk scheduler dan integration flow

## 20. Kesimpulan

Dengan constraint bisnis saat ini, langkah yang paling tepat bukan menyempurnakan global cycle lama, tetapi memindahkan lapisan scheduling menjadi merchant-aware.

Alasannya sederhana:
- akar delay `> 10 menit` sekarang lebih banyak datang dari urutan patroli dan biaya switch merchant,
- bukan dari rule `desired state` vs `live state` yang baru saja kita benahi.

Jadi strategi terbaik adalah:
- pertahankan engine yang sudah benar,
- ganti otak penjadwalannya.
