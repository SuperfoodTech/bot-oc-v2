# Pengumuman Rilis FoodMaster Bot-OC

## Bot-OC resmi digunakan

FoodMaster Bot-OC hadir sebagai pusat pengelolaan operasional outlet ShopeeFood. Tim admin dapat mengelola mitra, memantau outlet, dan mengatur status buka/tutup dari satu dashboard.

Mitra juga mendapatkan halaman khusus untuk melihat dan mengatur seluruh outlet yang menjadi tanggung jawabnya.

**Tanggal rilis:** 19 Agustus 2026  
**Nama rilis:** Bot-OC v0.2.26

## Apa yang baru?

- Login menggunakan akun Google untuk admin dan mitra.
- Dashboard admin untuk mengelola seluruh mitra dan outlet.
- Dashboard khusus mitra yang bisa dibuka melalui link pribadi.
- Satu mitra dapat mengelola beberapa outlet dalam satu halaman.
- Pengaturan buka otomatis untuk outlet.
- Fitur tutup sementara dan buka kembali.
- Pemantauan aktivitas outlet.
- Riwayat perubahan dan aktivitas yang lebih mudah ditelusuri.
- Pemantauan outlet agency dan outlet yang perlu diperhatikan.
- Proses tambah mitra dan outlet dalam satu alur yang lebih rapi.
- Link dashboard mitra dapat langsung dibuat dan disalin.
- Tampilan yang lebih nyaman digunakan melalui desktop maupun mobile.

## Login admin

Admin dapat masuk dengan dua cara:

1. Username dan password admin.
2. Tombol `Masuk dengan Google`.

Untuk menggunakan login Google, alamat email Google admin harus sudah didaftarkan oleh pihak yang berwenang.

## Login mitra

Mitra dapat masuk melalui link dashboard pribadi yang diberikan oleh admin.

Mitra juga dapat menggunakan tombol `Masuk dengan Google` apabila email Google-nya sudah didaftarkan.

Setiap link mengarah ke akun mitra yang sesuai. Jadi, mitra tidak akan masuk ke akun milik mitra lain.

## Cara kerja dashboard mitra

Satu mitra dapat memiliki beberapa outlet dalam satu dashboard.

Contoh:

```text
Mitra Vinicius
├── Outlet 1
├── Outlet 2
└── Outlet 3
```

Dari halaman tersebut, mitra dapat:

- Melihat daftar outlet.
- Melihat status operasional outlet.
- Mengaktifkan atau menonaktifkan buka otomatis.
- Menutup outlet untuk sementara.
- Membuka kembali outlet.
- Melihat aktivitas terbaru.

## Fitur untuk admin

### Pengelolaan mitra dan outlet

Admin dapat:

- Menambahkan mitra baru.
- Menambahkan outlet baru.
- Mengubah informasi mitra dan outlet.
- Melihat Store ID dan informasi merchant.
- Mengatur paket layanan dan masa berlaku.
- Mengubah email Google mitra.
- Mengubah passcode dashboard mitra.
- Menangguhkan outlet jika diperlukan.
- Memperpanjang masa layanan outlet.
- Menghapus outlet atau seluruh data mitra dengan konfirmasi.

### Tambah mitra dan outlet

Proses pendaftaran baru terdiri dari:

1. Mengisi data mitra.
2. Mengisi data outlet.
3. Memilih paket layanan.
4. Memeriksa kembali data.
5. Menyimpan data dan membuat link dashboard.

Informasi yang perlu disiapkan:

- Nama mitra.
- Email Google mitra jika akan menggunakan login Google.
- Passcode dashboard.
- Nama merchant.
- Nama outlet.
- Store ID ShopeeFood.
- Paket layanan.
- Tanggal mulai layanan.

Setelah proses selesai, link dashboard akan muncul di bagian review dan bisa langsung disalin.

## Pemantauan bot

Admin dapat melihat:

- Apakah bot sedang berjalan.
- Aktivitas terakhir bot.
- Outlet yang baru dibuka atau ditutup.
- Hasil tindakan bot.
- Riwayat aktivitas operasional.

Admin juga dapat menjalankan tindakan seperti memulai bot, menjeda bot, memperbarui informasi, atau menghentikan bot sesuai kebutuhan operasional.

## Pemantauan agency dan churn

Untuk outlet agency, tim dapat:

- Melihat daftar outlet agency.
- Memantau kondisi outlet secara berkala.
- Melihat outlet yang perlu ditindaklanjuti.
- Menutup outlet tertentu bila diperlukan.
- Mengaktifkan atau menonaktifkan pengaturan penutupan otomatis.

## Keamanan akses

- Admin hanya dapat masuk menggunakan akun admin.
- Mitra hanya dapat mengakses dashboard melalui link miliknya.
- Login Google hanya dapat digunakan oleh email yang sudah terdaftar.
- Setiap mitra memiliki link dashboard sendiri.
- Data mitra tidak ditampilkan pada link milik mitra lain.
- Penghapusan data membutuhkan konfirmasi admin.
- Tombol penghapusan tidak dapat diklik berulang kali saat proses sedang berjalan.

## Peningkatan tampilan dan pengalaman penggunaan

Pada rilis ini:

- Header menggunakan logo FoodMaster.
- Tampilan dashboard lebih bersih dan tidak menggunakan warna pastel berlebihan.
- Informasi status dibuat lebih sederhana.
- Tombol `Tutup sementara` tetap menggunakan warna merah karena berdampak langsung pada operasional outlet.
- Pesan berhasil dan pesan kesalahan lebih mudah dipahami.
- Tampilan menyesuaikan perangkat mobile dan desktop.
- Form yang belum selesai akan memberikan peringatan saat akan ditinggalkan.
- Setelah data berhasil disimpan, pengguna dapat kembali tanpa peringatan tambahan.

## Panduan singkat untuk tim

### Jika ingin menambahkan mitra

1. Buka dashboard admin.
2. Pilih `Tambah mitra`.
3. Isi data mitra, outlet, dan paket layanan.
4. Periksa kembali data pada bagian review.
5. Klik `Simpan & generate link`.
6. Salin link dashboard dan kirimkan kepada mitra.

### Jika mitra ingin mengatur outlet

1. Buka link dashboard mitra.
2. Masukkan passcode atau gunakan login Google.
3. Pilih outlet yang ingin diatur.
4. Gunakan tombol buka otomatis, tutup sementara, atau buka kembali sesuai kebutuhan.

### Jika outlet bermasalah

1. Periksa status outlet di dashboard admin.
2. Periksa apakah outlet sedang ditangguhkan.
3. Periksa riwayat aktivitas terakhir.
4. Jika diperlukan, admin dapat memperbarui data atau menghubungi tim terkait.

## Catatan penting

- Satu mitra dengan beberapa outlet menggunakan satu link dashboard.
- Jika setiap outlet harus memiliki akses terpisah, outlet tersebut perlu dibuatkan akun atau link yang berbeda.
- Login Google hanya dapat digunakan setelah email didaftarkan.
- Passcode dashboard harus dibagikan hanya kepada mitra yang bersangkutan.

## Penutup

Bot-OC membantu FoodMaster mengelola operasional outlet dengan lebih teratur, mempercepat proses pendaftaran mitra, dan memberikan akses yang lebih jelas bagi admin maupun mitra.
