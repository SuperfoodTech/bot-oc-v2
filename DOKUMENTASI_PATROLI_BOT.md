# Dokumentasi Mudah: Cara Main Bot dan Bot VB Melakukan Patroli

Dokumen ini menjelaskan alur patroli secara sederhana untuk tim operasional,
developer, dan admin dashboard.

## 1. Gambaran Singkat

Ada dua service patroli:

| Service | Tugas utama | Cara mengelompokkan patroli |
|---|---|---|
| `main-bot` | Mengelola outlet biasa dari dashboard Agency | Per akun Shopee dan portal merchant |
| `main-vb` | Mengelola outlet yang tergabung dalam Virtual Brand | Per portal merchant dalam satu brand VB |

Keduanya membaca state runtime dari PostgreSQL. Spreadsheet hanya digunakan
untuk import data, bukan sebagai sumber keputusan patroli harian.

Alur besarnya:

```text
Ambil data PostgreSQL
        |
        v
Baca desired state, live state, jadwal, pause, subscription, suspension
        |
        v
Tentukan keputusan bot
        |
        +--> Tidak perlu aksi: simpan state, tunggu jadwal berikutnya
        |
        +--> Perlu buka/tutup: jalankan aksi ke Shopee
                              |
                              v
                       Verifikasi live state
                              |
                              v
                       Simpan log dan jadwalkan patroli berikutnya
```

## 2. Dua State Penting

### Desired state

Target yang diinginkan oleh sistem:

- `OPEN`: outlet boleh otomatis buka mengikuti jadwal.
- `PAUSE`: outlet ditutup sementara sampai waktu tertentu.
- `MANUAL_OFF`: otomatisasi tidak aktif.

Desired state berasal dari toggle, pause admin/mitra, masa layanan, dan status
penangguhan.

### Live state

Kondisi terakhir yang terbaca langsung dari Shopee:

- `OPEN`: outlet sedang buka di Shopee.
- `PAUSE`: outlet sedang pause sementara di Shopee.
- `CLOSED`: outlet sedang tutup di Shopee.
- `UNKNOWN`: status belum berhasil dibaca.

Contoh:

```text
Desired = OPEN
Live    = CLOSED
Hasil   = ACTION_OPEN
```

Artinya toggle menginginkan outlet buka, tetapi kondisi nyata di Shopee masih
tutup. Bot akan mencoba membuka outlet.

## 3. Urutan Keputusan Bot

Untuk setiap outlet, bot mengevaluasi aturan berikut secara berurutan:

1. **Penangguhan admin**
   Jika outlet ditangguhkan, targetnya selalu tutup.

2. **Subscription**
   Jika masa layanan Auto Open sudah berakhir, otomatisasi tidak membuka outlet.

3. **Pause aktif**
   Jika ada pause sementara yang belum berakhir, outlet harus tetap tutup.

4. **Jadwal operasional Shopee**
   Di luar jam operasional, bot tidak memaksa outlet buka atau tutup. Bot
   menunggu sesi berikutnya.

5. **Toggle utama**
   Jika toggle aktif dan sedang berada di jam operasional, targetnya buka.
   Jika toggle nonaktif, targetnya tutup.

6. **Bandingkan dengan live state**
   Jika target dan live state sama, hasilnya `NO_CHANGE`.
   Jika berbeda, hasilnya `ACTION_OPEN` atau `ACTION_CLOSE`.

## 4. Cara `main-bot` Patroli

`main-bot` menangani outlet biasa di Agency.

### Alur satu siklus

```text
Ambil semua outlet aktif dari PostgreSQL
        |
        v
Kelompokkan berdasarkan akun Shopee + portal merchant
        |
        v
Pastikan session browser siap
        |
        v
Baca jadwal dan status live dari Shopee
        |
        v
Evaluasi decision engine per outlet
        |
        v
Jalankan aksi yang diperlukan
        |
        v
Catat hasil ke automation_logs
```

### Session dan merchant

- Satu browser dapat digunakan kembali untuk satu akun Shopee.
- Bot berpindah ke portal merchant yang sesuai sebelum memproses outlet.
- Jika session mati atau browser kehilangan konteks, bot mencoba recovery session.
- Akun yang tidak termasuk `ALLOWED_USERNAMES` tidak diproses.

### Eksekusi aksi

Bot mengutamakan aksi melalui request/XHR di browser yang sudah login.
Jika aksi gagal, bot mencatat kegagalan dan menjadwalkan pemeriksaan ulang.

Setelah aksi berhasil dikirim, bot mencoba membaca ulang status Shopee. Ini
penting karena aksi terkirim belum selalu berarti perubahan sudah terlihat live.

## 5. Cara `main-vb` Patroli

`main-vb` menangani brand Virtual Brand yang memiliki beberapa portal atau
Store ID.

### Alur satu siklus

```text
Ambil brand dan Store ID terkait
        |
        v
Bangun antrean per portal merchant
        |
        v
Pilih portal yang paling perlu diproses
        |
        v
Terapkan perubahan status brand yang masih pending
        |
        v
Switch ke portal merchant tersebut
        |
        v
Patroli semua Store ID pada portal itu
        |
        v
Baca jadwal + live state, evaluasi, eksekusi, verifikasi
        |
        v
Pindah ke portal berikutnya
```

### Mengapa VB dipatroli per portal?

Satu brand VB dapat berisi beberapa portal, contohnya:

```text
Lakubudi
|- SuperFood
|- WonderFood
|- Lokarasa
`- Gurame Bakar, Do Eat
```

Bot tidak perlu login atau switch merchant untuk setiap Store ID. Bot switch
sekali ke portal merchant, lalu memproses Store ID yang berada di portal itu.
Ini mengurangi waktu patroli dan mengurangi risiko context merchant tertukar.

Urutan portal pada dashboard tidak mengubah aturan keputusan bot. Urutan hanya
untuk memudahkan pembacaan manusia; scheduler tetap memilih berdasarkan
prioritas dan waktu jatuh tempo patroli.

### Perubahan status brand VB

Ketika admin menekan toggle brand:

1. Dashboard menyimpan `requested_status`.
2. Status belum langsung dianggap sudah diterapkan di Shopee.
3. Saat brand mendapat giliran patroli, bot menerapkan perubahan ke
   `applied_status`.
4. Outlet di dalam brand kemudian diproses satu per satu.
5. Dashboard memperlihatkan perbedaan desired dan live melalui fase bot.

Contoh status transisi:

```text
Desired brand = PAUSE
Live outlet   = OPEN
Status UI     = Sedang Buka - Menunggu bot menutup
```

Ini bukan otomatis berarti failure. Ini adalah state normal ketika permintaan
sudah tersimpan tetapi bot belum menyelesaikan aksi.

## 6. Retry dan Recovery

Bot melakukan retry pada beberapa kondisi penting:

- Browser session mati.
- Switch portal gagal.
- Jadwal Shopee belum tersedia.
- Live state belum dapat dibaca.
- Eksekusi buka/tutup gagal.
- Status setelah aksi belum sesuai target.

Retry tidak selalu berarti langsung mengulang tanpa jeda. Scheduler menghitung
waktu pemeriksaan berikutnya berdasarkan:

- Awal sesi operasional berikutnya.
- Berakhirnya pause.
- Kebutuhan verifikasi setelah aksi.
- Heartbeat outlet yang sedang aktif.

## 7. Arti Status di Dashboard

### Status portal

Status di tabel menunjukkan kondisi live dan fase bot, misalnya:

- `Sedang Buka`: live state buka dan sudah sesuai.
- `Sedang Tutup`: live state tutup.
- `Sedang Buka - Menunggu bot menutup`: target tutup, tetapi live masih buka.
- `Sedang Tutup - Menunggu bot membuka`: target buka, tetapi live masih tutup.
- `Sedang Tutup - Di luar jadwal`: belum waktunya outlet buka.
- `Status sedang dicek bot`: data live atau jadwal belum tersedia.

### Failure

`Failure` hanya berarti ada kegagalan patroli atau eksekusi yang tercatat,
bukan sekadar desired state dan live state sedang berbeda.

Contoh yang **bukan** failure:

```text
Toggle meminta tutup
Live masih buka
Bot masih menunggu giliran patroli
```

Contoh failure:

```text
Bot mencoba menutup outlet
Aksi Shopee gagal atau verifikasi pasca-aksi gagal
Kegagalan dicatat di automation_logs
```

## 8. Contoh Skenario

### Skenario A: Outlet normal buka

```text
Toggle       = ON
Jam          = sedang berjalan
Live Shopee  = OPEN
Keputusan    = NO_CHANGE
```

Bot tidak mengirim aksi baru. Bot hanya melanjutkan heartbeat atau pemeriksaan
berikutnya.

### Skenario B: Jadwal baru dimulai

```text
Toggle       = ON
Jam          = baru masuk jam buka
Live Shopee  = CLOSED
Keputusan    = ACTION_OPEN
```

Bot membuka outlet, membaca ulang status, lalu menyimpan hasilnya.

### Skenario C: Pause sementara

```text
Pause        = aktif sampai 14:00
Live Shopee  = OPEN
Keputusan    = ACTION_CLOSE
```

Bot menutup outlet. Setelah pause berakhir, scheduler menjadwalkan evaluasi
berikutnya.

### Skenario D: Perubahan status brand VB

```text
Admin        = klik Tutup pada brand VB
Brand        = requested PAUSED
Patroli      = belum mendapat giliran
Dashboard    = menunggu bot
```

Saat giliran brand datang, `main-vb` menerapkan status brand dan memproses
outlet-outlet di dalamnya.

## 9. Lokasi Kode Penting

| Bagian | Lokasi |
|---|---|
| Decision engine bersama | `src/core/decision.py` |
| Worker outlet biasa | `main-bot/src/worker.py` |
| Scheduler outlet biasa | `main-bot/src/scheduler.py` |
| Daemon outlet biasa | `main-bot/src/daemon.py` |
| Worker VB | `main-vb/src/backend/worker.py` |
| Scheduler VB | `main-vb/src/scheduler.py` |
| Daemon VB | `main-vb/src/daemon.py` |
| State dan log VB | `main-vb/src/db.py` dan `main-vb/src/backend/db.py` |
| Decision status dashboard | `src/backend/templates/admin_dashboard.html` |

## 10. Ringkasan untuk Operasional

- Jangan menganggap status menunggu bot sebagai failure.
- Lihat `desired state` untuk mengetahui target sistem.
- Lihat `live state` untuk mengetahui kondisi nyata di Shopee.
- Bot bekerja berdasarkan jadwal dan prioritas, bukan hanya interval tetap.
- `main-bot` bekerja untuk outlet biasa.
- `main-vb` bekerja per portal merchant untuk outlet yang tergabung dalam VB.
- Jika aksi gagal, cek `automation_logs` dan status verifikasi pasca-aksi.
