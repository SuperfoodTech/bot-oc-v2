# After Build: Cara Kerja Bot Setelah Merchant-Aware Scheduler

Dokumen ini menjelaskan perilaku bot setelah perubahan `desired state/live
state`, perbaikan multi-schedule, dan penerapan merchant-aware scheduler.

## 1. Arsitektur Saat Ini

```text
Database runtime
  -> scheduler menghitung due_at dan prioritas outlet
  -> outlet digabung menjadi merchant group
  -> merchant paling urgent dipilih
  -> worker memproses semua outlet di merchant tersebut
  -> database dibaca ulang
  -> scheduler menghitung ulang antrean
```

Perubahan inti:

- Unit antrean adalah `(username, nama_portal)`, bukan outlet tunggal.
- Urgency tetap dihitung dari kondisi masing-masing outlet.
- Semua outlet dalam merchant yang sama diproses dalam satu context Shopee.
- Scheduler melakukan refresh setelah setiap merchant group.
- Mismatch baru dapat langsung naik prioritas tanpa menunggu global cycle penuh.
- Endpoint manual `/bot/sync` tetap memakai full sync untuk kompatibilitas.

## 2. Desired State dan Live State

Desired state adalah target internal, sedangkan live state adalah fakta terakhir
yang terbaca dari Shopee. Bot tidak menimpa fakta live dengan target.

| Desired state | Arti |
|---|---|
| `OPEN` | Outlet harus terbuka saat jadwal aktif dan toggle ON. |
| `PAUSE` | Outlet harus tertutup sampai `pause_until`. |
| `MANUAL_OFF` | Otomatisasi tidak meminta outlet dibuka. |

| Live state | Arti |
|---|---|
| `OPEN` | Shopee sedang membuka outlet. |
| `PAUSE` | Shopee sedang menutup outlet melalui pause. |
| `CLOSED` | Shopee sedang menutup outlet. |
| `UNKNOWN` | Status belum berhasil dibaca. |

Aturan praktisnya:

- Desired `OPEN` + live `CLOSED/PAUSE` + masih dalam jadwal: mismatch, lakukan
  open.
- Desired tutup + live `OPEN`: mismatch, lakukan close/pause.
- Desired `PAUSE` + live `PAUSE/CLOSED`: sudah sinkron, tetapi pause boundary
  tetap dijadwalkan.
- Desired `OPEN` + live `CLOSED` + di luar jadwal: normal, tunggu jadwal buka.
- Desired `MANUAL_OFF` + live tutup: sinkron, jangan membuka outlet.

## 3. Alur Daemon

Saat startup, daemon mengambil single-instance lock, menginisialisasi DB,
melakukan warmup session Shopee, lalu membangun queue dari outlet runtime.

Untuk setiap dispatch:

1. Scheduler membaca outlet terbaru dari DB.
2. Setiap outlet diberi `due_at`, priority, alasan, dan status actionable.
3. Outlet dengan merchant key sama digabung menjadi satu queue item.
4. Group dengan priority tertinggi dan `due_at` terdekat dipilih.
5. Worker memproses group tersebut.
6. Daemon membaca DB kembali dan menghitung queue ulang.
7. Jika masih ada group due, dispatch dilanjutkan tanpa tidur interval penuh.
8. Jika belum ada group due, daemon tidur sampai due time terdekat.

Mode `--once` hanya melakukan satu merchant dispatch, sedangkan mode normal
terus menguras group yang sedang due lalu menunggu jadwal berikutnya.

## 4. Prioritas Scheduler

| Priority | Kondisi | Next check |
|---:|---|---|
| 100 | Desired `OPEN`, live tutup saat jadwal aktif | Sekarang |
| 95 | Desired tutup, live `OPEN` | Sekarang |
| 80 | Pause aktif dan ada sesi berikutnya sebelum pause berakhir | Boundary sesi |
| 70 | Pause aktif tanpa sesi berikutnya sebelum pause berakhir | `pause_until` |
| 60 | Desired `OPEN` di luar jadwal | Jadwal reguler berikutnya |
| 40 | Outlet buka dan sinkron | Sekitar 180 detik |
| 30 | Jadwal Shopee belum tersedia | Sekitar 60 detik |
| 10 | Outlet tutup dan tidak membutuhkan action | Sekitar 600 detik |

Worker tetap menangani recheck pasca-action. Jika action gagal, verification
belum terbaca, atau hasil live tidak sesuai target, worker meminta wake-up cepat
untuk percobaan berikutnya.

## 5. Perilaku Worker Per Merchant

Worker tidak berpindah merchant untuk setiap outlet. Urutannya:

1. Memfilter outlet ke target merchant group.
2. Memastikan browser/session akun masih hidup.
3. Memeriksa merchant context dan switch hanya jika diperlukan.
4. Memastikan halaman Business Hours cocok dengan `storeId` target.
5. Mengambil jadwal Shopee dan mempertahankan jadwal valid terakhir jika fetch
   sementara gagal.
6. Membaca live state outlet.
7. Mengevaluasi desired/live state.
8. Mengirim open atau pause bila diperlukan.
9. Membaca ulang live state setelah action.
10. Hanya menulis live state baru ke DB jika verification berhasil.

Jika session mati di tengah group, worker mencoba recovery. Jika recovery gagal,
outlet tidak dianggap sukses; group akan mendapat kesempatan pada dispatch
berikutnya.

## 6. Contoh Random Close Shopee

Kondisi:

- Jadwal `09:00-21:00`.
- Jam sekarang `12:10`.
- Toggle dashboard `ON`.
- Live Shopee `CLOSED`.

Alur:

1. Scheduler menganggap desired `OPEN`, live `CLOSED`, masih dalam jadwal.
2. Outlet mendapat priority `100` dan `due_at=now`.
3. Merchant group outlet tersebut dipilih sebelum heartbeat normal.
4. Worker menjalankan `ACTION_OPEN`.
5. Worker memverifikasi status live.
6. Jika live sudah `OPEN`, DB diperbarui ke `ON`.
7. Jika verification belum berhasil, DB tidak dipaksa menjadi `ON` dan worker
   meminta recheck.

Selama proses belum selesai, dashboard menampilkan:

`Sedang Tutup • Menunggu bot membuka`

Artinya live state masih tutup, tetapi target internal sudah buka dan bot sedang
mengoreksinya.

## 7. Contoh Pause Multi-Schedule

Kondisi:

- Jadwal: `12:00-13:40` dan `14:00-15:00`.
- User meminta pause pada `13:30` sampai `14:30`.

Alur:

1. Desired state menjadi `PAUSE`.
2. Jika outlet masih `OPEN`, bot segera mengirim pause.
3. Pada `13:40-14:00`, Shopee menutup outlet karena break normal.
4. Scheduler menemukan sesi berikutnya `14:00`, yang masih sebelum `14:30`.
5. Group mendapat `due_at=14:00` dan priority `80`.
6. Saat sesi kedua mulai, worker membaca live state lagi.
7. Jika Shopee membuka outlet otomatis, desired `PAUSE` dan live `OPEN` menjadi
   mismatch priority `95`; bot mengirim pause ulang.
8. Outlet dijaga tutup sampai pause berakhir.

Sesi kedua tidak dapat menghapus desired pause hanya karena Shopee membuka
outlet secara otomatis.

## 8. Contoh Banyak Outlet dan Merchant

Merchant A memiliki A1 dan A2, sedangkan Merchant B memiliki B1.

- A1 random close: priority `100`.
- A2 heartbeat: priority `40`.
- B1 random close: priority `100`.

Scheduler membuat satu queue item untuk A dan satu untuk B. Worker masuk ke A
satu kali lalu memproses A1 dan A2 tanpa switch per outlet. Setelah A selesai,
state di-refresh dan scheduler memilih antara B atau group lain berdasarkan
kondisi terbaru.

Jika sebuah merchant memiliki banyak outlet, seluruh outlet group tetap diproses
bersama. Tradeoff-nya, merchant group yang sangat besar masih dapat membuat
boundary merchant lain menunggu sampai group itu selesai.

## 9. Boundary Terlewati Saat Cycle Berjalan

Misalnya sesi berikutnya dimulai `14:00`, tetapi group besar selesai pada
`14:03`.

Bot belum mem-preempt action yang sedang berjalan. Namun worker membandingkan
waktu mulai dan selesai cycle. Jika boundary sudah lewat, wake hint dibuat cepat
dan daemon segera menghitung ulang queue. Jadi boundary tidak menambah satu
interval panjang lagi setelah group selesai.

Gap tetap mungkin sebesar durasi group yang sedang aktif. Ini adalah limitation
yang berbeda dari bug lama, ketika bot masih dapat tidur satu interval penuh
setelah boundary terlewati.

## 10. Label Dashboard

| Label | Makna |
|---|---|
| `Sedang Buka` | Live Shopee buka dan tidak ada mismatch. |
| `Sedang Tutup` | Live Shopee tutup tanpa konteks pending khusus. |
| `Tutup Sementara` | Pause aktif dan live state sudah tutup. |
| `Sedang Buka • Menunggu bot menutup` | Target tutup, live masih buka. |
| `Sedang Tutup • Menunggu bot membuka` | Target buka, live masih tutup saat jadwal aktif. |
| `Sedang Tutup • Di luar jadwal` | Tutup normal karena di luar jadwal Shopee. |
| `Sedang Tutup • Otomatisasi nonaktif` | Toggle automation OFF. |
| `Sedang Tutup • Dinonaktifkan admin` | Outlet ditangguhkan admin. |
| `Status sedang dicek bot` | State atau jadwal belum cukup valid. |

`Menunggu bot membuka/menutup` menunjukkan pekerjaan bot belum selesai.
`Di luar jadwal` bukan error dan tidak dilawan bot.

## 11. Edge Case yang Sudah Ditangani

| Edge case | Perilaku sekarang |
|---|---|
| Shopee random close saat toggle ON | Dianggap mismatch ketika jadwal aktif dan diprioritaskan. |
| Pause melewati break multi-schedule | Recheck dijadwalkan pada sesi berikutnya sebelum pause berakhir. |
| Boundary lewat di tengah cycle | Wake-up dipercepat setelah cycle selesai. |
| DB menulis target tanpa live verification | Tidak dilakukan; state live hanya diubah setelah verification. |
| Dua sync overlap dalam process | `SYNC_LOCK` mencegah eksekusi bersamaan. |
| Salah merchant atau outlet context | Merchant context dan `storeId` divalidasi sebelum fetch/action. |
| Session browser mati | Recovery dicoba sebelum melanjutkan. |
| Fetch jadwal sementara gagal, kosong, atau malformed | Jadwal valid terakhir dipertahankan; hanya payload dengan interval valid yang boleh menggantikan cache. |
| Pause expired di dashboard | Endpoint admin menyinkronkan pause expired sebelum response. |
| Overnight Shopee | Tidak memakai satu interval overnight; lintas tengah malam dibuat dua jadwal. |

## 12. Known Limitation

- Belum ada webhook atau watcher real-time dari Shopee.
- Shopee dapat menutup outlet sesaat setelah patrol; bot menangkapnya pada
  dispatch berikutnya.
- Group merchant yang sangat besar belum dipecah menjadi batch preemptive.
- `SYNC_LOCK` dan daemon lock tidak menggantikan distributed lock lintas host
  atau container.
- Action yang terus ditolak Shopee tetap membutuhkan diagnosis dari log dan
  post-action verification.
- Data account, jadwal, dan merchant yang salah di database tetap dapat
  menyebabkan session atau routing salah.

Target operasionalnya adalah delay normal sekitar `1-5 menit`. Kasus di atas
`10 menit` perlu diperiksa melalui durasi merchant group, status session,
ketersediaan jaringan, dan hasil verification action.

## 13. File Implementasi dan Verifikasi

- `main-bot/src/scheduler.py`: due state, priority, queue, dan next wake.
- `main-bot/src/daemon.py`: dispatch merchant-aware dan refresh queue.
- `main-bot/src/worker.py`: session, context merchant, action, dan verification.
- `src/core/decision.py`: desired/live decision dan schedule boundary.
- `src/backend/db.py`: runtime state dan label dashboard.

Verifikasi build terakhir:

```text
25 passed
python compile check: berhasil
git diff --check: bersih
```
