# Dokumentasi Pengguna FoodMaster Bot O/C

## 1. Untuk siapa dokumen ini

Dokumen ini ditujukan untuk:

- admin operasional FoodMaster,
- tim internal yang mengelola Virtual Brand,
- mitra/merchant yang memakai dashboard outlet.

## 2. Ringkasan peran

| Peran | Akses utama | Bisa melakukan apa |
|---|---|---|
| Admin | `/admin/login` lalu `/admin/dashboard` | Lihat outlet, fetch data, kontrol toggle outlet, kontrol VB, lihat log, kontrol bot, kelola akun admin, hapus outlet/merchant |
| Mitra | `/mitra/{slug}` atau `/app` | Login pakai passcode, lihat outlet sendiri, menutup sementara outlet, membuka kembali outlet, melihat aktivitas terbaru |
| Bot reguler | background service | Menjaga outlet reguler tetap sesuai desired state |
| Bot VB | background service | Menjaga outlet anggota Virtual Brand sesuai status brand |

## 3. Cara masuk ke sistem

### 3.1 Admin

1. Buka `http://localhost:3001/admin/login`.
2. Masukkan `username` dan `password` admin.
3. Jika Google Auth diaktifkan oleh environment, login Google dapat digunakan untuk akun yang email-nya sudah didaftarkan.

### 3.2 Mitra

1. Buka link dashboard yang diberikan admin, biasanya berbentuk `/mitra/{slug}`.
2. Masukkan passcode mitra.
3. Setelah berhasil login, mitra akan melihat:
   - nama mitra,
   - status subscription,
   - jumlah outlet,
   - daftar outlet,
   - aktivitas terbaru.

## 4. Panduan admin dashboard

### 4.1 Tab utama

Dashboard admin saat ini berpusat pada empat area:

1. `Operasional Outlet`
2. `Virtual Brand`
3. `Logs`
4. `Settings`

### 4.2 Operasional Outlet

Di tab ini admin bisa:

- melihat semua outlet reguler yang aktif,
- memfilter berdasarkan owner, outlet, store ID, status, subscription, dan paket,
- membuka detail outlet,
- mengubah toggle outlet,
- menutup sementara banyak outlet sekaligus,
- menghapus outlet.

#### Cara memakai toggle outlet

1. Toggle `ON` berarti desired state outlet adalah buka otomatis.
2. Toggle `OFF` berarti outlet ditutup sementara atau otomatisasi dimatikan.
3. Saat menutup outlet, admin dapat memilih:
   - `30 Menit`
   - `60 Menit`
   - `Sepanjang Hari`
   - `Durasi lain`

Catatan penting:

- `ON` tidak selalu berarti live Shopee langsung buka saat itu juga. Bot masih harus menjalankan patroli dan aksi ke Shopee.
- Admin tidak bisa memaksa outlet reguler buka di luar jadwal operasional atau saat jadwal Shopee belum siap.

#### Bulk action

1. Klik `Pilih beberapa`.
2. Centang outlet yang ingin diproses.
3. Gunakan `Buka terpilih` atau `Tutup terpilih`.

### 4.3 Virtual Brand

Tab `Virtual Brand` dipakai untuk grup brand yang berisi banyak store lintas portal.

Admin dapat:

- melihat statistik brand aktif,
- memfilter berdasarkan nama grup, status master, status grup, portal, dan store ID,
- meminta brand dibuka atau ditutup,
- melihat jadwal store anggota melalui drawer jadwal,
- menjalankan bulk action beberapa brand sekaligus.

Cara baca status brand:

1. Toggle di UI menyimpan `requested_status`.
2. Daemon VB akan mengubahnya menjadi `applied_status` saat brand itu diproses.
3. Karena itu, sesaat setelah toggle diubah, outlet anggota brand masih bisa terlihat belum sinkron. Ini normal.

### 4.4 Logs

Tab `Logs` dipakai untuk:

- melihat jumlah event `Bot O/C` dan `Virtual Brand`,
- melihat error terbaru,
- melihat activity terakhir bot,
- melihat countdown menuju cycle berikutnya.

Jika ada masalah operasional, tab ini adalah tempat pertama yang harus dicek.

### 4.5 Settings

Di tab `Settings`, admin dapat:

- mengganti username admin sendiri,
- mengganti password admin sendiri,
- menambah akun admin baru,
- melihat daftar admin terdaftar,
- logout dari dashboard.

## 5. Panduan mitra dashboard

### 5.1 Halaman utama

Setelah login, mitra akan melihat:

- ringkasan akun,
- status subscription,
- passcode akun,
- daftar outlet,
- histori aktivitas terbaru.

### 5.2 Menghidupkan buka otomatis

1. Cari outlet yang ingin dibuka.
2. Nyalakan toggle `Buka otomatis`.
3. Sistem akan menyimpan permintaan buka dan bot akan membuka outlet bila syarat runtime terpenuhi.

Syarat utamanya:

- outlet tidak sedang ditangguhkan admin,
- subscription outlet masih aktif,
- jadwal reguler Shopee sudah tersedia,
- waktu sekarang berada dalam jam operasional Shopee.

### 5.3 Menutup sementara outlet

1. Matikan toggle outlet.
2. Pilih durasi pause:
   - `30 Menit`
   - `60 Menit`
   - `Sepanjang Hari`
   - `Durasi lain`
3. Konfirmasi permintaan.

Setelah itu:

- permintaan tutup tersimpan,
- bot akan menutup outlet,
- outlet akan dibuka kembali otomatis setelah `pause_until` berlalu.

### 5.4 Membuka kembali outlet

1. Jika outlet sedang pause, nyalakan kembali toggle.
2. Mitra akan melihat modal konfirmasi buka.
3. Setelah konfirmasi, bot akan memproses pembukaan outlet.

### 5.5 Aktivitas terbaru

Bagian `Aktivitas terbaru` menampilkan riwayat seperti:

- `Ditutup sementara`
- `Dibuka kembali manual`
- `ACTION_OPEN`
- `ACTION_CLOSE`

Log ini membantu mitra memahami apakah perubahan sudah sekadar diminta atau benar-benar sudah dikerjakan bot.

## 6. Arti status yang muncul di UI

| Status | Arti praktis |
|---|---|
| `Sedang Buka` | Live Shopee sudah buka dan sesuai target |
| `Sedang Tutup - Menunggu bot membuka` | Desired state buka, tetapi live Shopee masih tutup |
| `Sedang Buka - Menunggu bot menutup` | Desired state tutup, tetapi live Shopee masih buka |
| `Tutup Sementara` | Outlet sedang pause dan bot/life state sudah sinkron |
| `Sedang Tutup - Di luar jadwal` | Toggle bisa tetap bermakna buka, tetapi sekarang di luar jadwal Shopee |
| `Menunggu fetch jadwal` | Bot belum punya jadwal Shopee yang valid |
| `Gagal fetch jadwal, bot akan coba lagi` | Fetch jadwal sempat gagal dan akan diulang |
| `Jadwal Shopee belum diatur` | Bot berhasil cek, tetapi jadwal Shopee memang kosong |
| `Sedang Tutup - Otomatisasi nonaktif` | Toggle off tanpa pause aktif atau subscription outlet sudah berakhir |
| `Sedang Tutup - Dinonaktifkan admin` | Outlet ditahan di level admin/suspension |
| `Status sedang dicek bot` | Live state belum tersedia atau sedang disinkronkan ulang |

## 7. Arti alasan toggle terkunci

| Alasan | Artinya |
|---|---|
| `OUTSIDE_SCHEDULE` | Sekarang bukan jam operasional Shopee |
| `NOT_FETCHED_YET` | Jadwal Shopee belum pernah berhasil diambil |
| `FETCH_RETRYING` | Jadwal Shopee sedang gagal fetch dan akan dicoba ulang |
| `FETCHED_EMPTY` | Jadwal Shopee kosong di sisi Shopee |
| `SUSPENDED` | Outlet ditangguhkan admin |

## 8. Hal yang sengaja dibatasi di versi sekarang

1. Master data Agency tidak diedit dari dashboard. Perubahan owner, portal, store ID, paket, atau masa layanan harus dilakukan di Google Sheet lalu di-fetch ulang.
2. Beberapa form admin lama untuk tambah/edit/suspend/renew masih terlihat di UI, tetapi backend aktif saat ini menolaknya dengan `403`.
3. Mitra tidak dapat mengubah password akun sendiri.
4. Mitra tidak dapat membuka outlet jika outlet sedang suspend, di luar jadwal, atau jadwal Shopee belum valid.

## 9. FAQ singkat

### 9.1 Kenapa toggle sudah ON tapi outlet masih tutup?

Karena toggle hanya menyimpan desired state. Outlet baru benar-benar buka setelah:

- bot mendapat giliran patroli,
- live state dibaca,
- dan aksi `OPEN` berhasil dikirim ke Shopee.

### 9.2 Kenapa outlet tidak bisa dibuka malam hari?

Karena dashboard mengikuti jadwal operasional Shopee. Di luar jadwal, toggle sengaja dikunci.

### 9.3 Kenapa status bilang `Jadwal Shopee belum diatur`?

Bot sudah berhasil fetch schedule, tetapi dari Shopee memang tidak ada regular hours yang aktif untuk store itu.

### 9.4 Siapa yang harus dihubungi kalau outlet `Dinonaktifkan admin`?

Mitra harus menghubungi CS atau admin FoodMaster. Status ini tidak bisa dibuka sendiri dari dashboard mitra.

## 10. Troubleshooting cepat untuk pengguna

### 10.1 Admin

- Jika data outlet belum muncul: lakukan `Fetch dari Sheet`.
- Jika bot terlihat diam: cek tab `Logs`, lalu cek status bot.
- Jika hapus outlet gagal: kemungkinan Apps Script write-back belum dikonfigurasi atau sedang error.

### 10.2 Mitra

- Jika login gagal: pastikan passcode benar atau minta admin cek ulang link/passcode.
- Jika toggle tidak bisa dipakai: baca pesan status jadwal atau hubungi admin.
- Jika outlet lama tidak berubah: tunggu patroli berikutnya, lalu refresh halaman.
