**LOGIKA SISTEM**

**Database**
[**https://docs.google.com/spreadsheets/d/10osh4rI4q\_mv6fBe9NurXRztRrGa85L01Bwned6m0Qs/edit?usp=sharing**](https://docs.google.com/spreadsheets/d/10osh4rI4q_mv6fBe9NurXRztRrGa85L01Bwned6m0Qs/edit?usp=sharing)

**1\. VERCEL TOGGLE**

Vercel Toggle menjadi source of truth utama untuk status outlet.

Jika Vercel Toggle \= ON:
→ Bot memastikan ShopeePartner Toggle \= ON.
→ Jika ShopeePartner Toggle berubah menjadi OFF, bot mengubahnya kembali menjadi ON.
→ Berlaku selama masih dalam jam operasional.

Jika Vercel Toggle \= OFF:
→ Bot memastikan ShopeePartner Toggle \= OFF.
→ Jika ShopeePartner Toggle berubah menjadi ON, bot mengubahnya kembali menjadi OFF.

Jika jam operasional telah berakhir:
→ Sistem mengubah Vercel Toggle menjadi OFF.
→ Bot kemudian mengubah ShopeePartner Toggle menjadi OFF.

**2\. STATUS PENANGGUHAN**

Status Penangguhan hanya dapat diatur secara manual oleh Admin FoodMaster.

Pilihan:
\- Ya
\- Tidak

Jika Status Penangguhan \= Ya:
→ Admin FoodMaster mengubah Vercel Toggle menjadi OFF.
→ Karena Vercel Toggle \= OFF, bot memastikan ShopeePartner Toggle selalu OFF.
→ Jika outlet dibuka kembali melalui ShopeePartner, bot akan menutupnya kembali.

Jika Status Penangguhan \= Tidak:
→ Admin mencabut status penangguhan.
→ Admin dapat mengatur kembali Vercel Toggle sesuai kondisi outlet.
→ ShopeePartner Toggle kembali mengikuti status Vercel Toggle.

**3\. AUTO OPEN**

Auto Open adalah layanan berbayar.

Syarat Auto Open berjalan:
→ Status Penangguhan \= Tidak.
→ Subscription masih aktif.
→ Vercel Toggle \= ON.
→ Masih dalam jam operasional.

Hasil:
→ Bot memastikan ShopeePartner Toggle tetap ON.

**4\. AUTO CLOSE**

Auto Close digunakan untuk merchant yang sedang ditangguhkan.

Proses:
→ Admin mengubah Status Penangguhan menjadi Ya.
→ Admin mengubah Vercel Toggle menjadi OFF.
→ Bot memastikan ShopeePartner Toggle tetap OFF.
→ Bot terus menutup kembali outlet jika dibuka melalui ShopeePartner.

**5\. PRIORITAS SISTEM**

~~1\. Status Penangguhan~~
**2\. Status subscription**
**3\. Vercel Toggle sebagai source of truth**
4\. Jam operasional
5\. ShopeePartner Toggle sebagai status aktual outlet

*Lampiran fitur ketika mau menutup outlet di Vercel mengacu pada fitur ShopeePartner*
![][image1]
![][image2]

**FEATURE REQUIREMENT**
**FoodMaster Auto Open & Auto Close Bot — ShopeeFood**

**1\. TUJUAN**

Membuat bot automation yang dapat membuka dan menutup outlet ShopeeFood secara otomatis berdasarkan Vercel Toggle.

Vercel Toggle menjadi source of truth untuk menentukan status outlet di ShopeePartner.

Sistem memiliki dua fungsi:

1\. Auto Open
Layanan berbayar untuk memastikan outlet tetap terbuka selama jam operasional.

2\. Auto Close
Fitur internal FoodMaster untuk menjaga outlet tertentu tetap tertutup ketika sedang dalam Status Penangguhan.

**2\. MODEL LAYANAN AUTO OPEN**

Harga dasar layanan Auto Open adalah Rp1.000 per hari per outlet ShopeeFood.

Pilihan paket:

Paket 3 Bulan
\- Harga: Rp90.000
\- Bonus: Tidak ada
\- Total masa aktif: 3 bulan
\- Harga efektif: Rp1.000 per hari

Paket 6 Bulan
\- Harga: Rp180.000
\- Bonus: Tambahan 1 bulan
\- Total masa aktif: 7 bulan
\- Harga efektif: Rp857 per hari

Paket 12 Bulan
\- Harga: Rp360.000
\- Bonus: Tambahan 4 bulan
\- Total masa aktif: 16 bulan
\- Harga efektif: Rp750 per hari

Pembayaran dilakukan di awal sesuai paket yang dipilih.

Fitur Auto Close tidak dikenakan biaya karena digunakan sebagai kontrol internal FoodMaster.

**3\. FLOW MERCHANT AUTO OPEN**

1\. Merchant mengetahui layanan melalui aktivitas marketing.
2\. Merchant menghubungi FoodMaster.
3\. Merchant memilih paket 3, 6, atau 12 bulan.
4\. Merchant melakukan pembayaran.
5\. Merchant mengundang nomor HP FoodMaster sebagai Staff di akun ShopeePartner-nya.
6\. Merchant memberikan data berikut:
   \- Nama portal
   \- Nama panjang outlet
   \- Nama pendek outlet
   \- Merchant ID
   \- Store ID
   \- Jam operasional
7\. Tim FoodMaster memasukkan data ke dalam sistem.
8\. Tim FoodMaster membuat password dashboard untuk merchant.
9\. Merchant dapat mengatur Vercel Toggle melalui dashboard.

**4\. MERCHANT DASHBOARD**

Dashboard dibuat dalam bentuk website dan di-deploy melalui Vercel.

Merchant wajib memasukkan password untuk mengakses dashboard.

Dashboard menampilkan:
\- Nama portal
\- Nama panjang outlet
\- Nama pendek outlet
\- Merchant ID
\- Store ID
\- Jam operasional
\- Masa aktif langganan Auto Open
\- Vercel Toggle ON/OFF
\- Pilihan 30 menit, 60 menit, Sepanjang Hari, Waktu Lain saat melakukan Vercel Toggle OFF
\- Status ShopeePartner Toggle terakhir
\- Waktu pengecekan terakhir

Merchant hanya dapat melihat outlet miliknya sendiri.

Merchant tidak dapat mengubah Status Penangguhan.

**5\. DUA STATUS TOGGLE**

Sistem memiliki dua status toggle:
1\. Vercel Toggle
   \- Berada di dashboard Vercel.
   \- Menjadi source of truth.
   \- Memiliki pilihan ON atau OFF.
2\. ShopeePartner Toggle
   \- Menunjukkan status aktual outlet di ShopeePartner.
   \- Dibaca dan diubah oleh bot agar sesuai dengan Vercel Toggle.

**6\. FUNGSI VERCEL TOGGLE**

Jika Vercel Toggle \= ON:
\- Bot memastikan ShopeePartner Toggle \= ON.
\- Jika ShopeePartner Toggle berubah menjadi OFF, bot mengubahnya kembali menjadi ON.
\- Auto Open hanya berjalan selama subscription aktif dan masih dalam jam operasional.

Jika Vercel Toggle \= OFF:
\- Bot memastikan ShopeePartner Toggle \= OFF.
\- Jika ShopeePartner Toggle berubah menjadi ON, bot mengubahnya kembali menjadi OFF.

Jika jam operasional telah dimulai:
\- Sistem mengubah Vercel Toggle menjadi ON.
\- Bot mengubah ShopeePartner Toggle menjadi ON.

Jika jam operasional telah berakhir:
\- Sistem mengubah Vercel Toggle menjadi OFF.
\- Bot mengubah ShopeePartner Toggle menjadi OFF.

**7\. STATUS PENANGGUHAN**

Status Penangguhan hanya dapat diatur secara manual oleh Admin FoodMaster.

Pilihan Status Penangguhan:
\- Ya
\- Tidak

Jika Status Penangguhan \= Ya:
\- Admin mengubah Vercel Toggle menjadi OFF.
\- Bot memastikan ShopeePartner Toggle selalu OFF.
\- Jika outlet dibuka kembali melalui ShopeePartner, bot akan menutupnya kembali.
\- Bot terus menjaga outlet tetap tertutup sampai penangguhan dicabut.

Jika Status Penangguhan \= Tidak:
\- Admin mencabut penangguhan.
\- Admin dapat mengatur kembali Vercel Toggle sesuai kondisi outlet.
\- ShopeePartner Toggle kembali mengikuti Vercel Toggle.

Status Penangguhan dapat digunakan untuk merchant yang churn atau memiliki kewajiban kepada FoodMaster.

**8\. AUTOMATION LOGIC**

Bot melakukan pengecekan status outlet secara berkala.

Logika dasar:
1\. Membaca Status Penangguhan.
2\. Membaca status subscription Auto Open.
3\. Membaca Vercel Toggle.
4\. Membaca jam operasional.
5\. Memeriksa ShopeePartner Toggle.
6\. Menyesuaikan ShopeePartner Toggle berdasarkan Vercel Toggle.

Logika Auto Open:

Jika:
\- Status Penangguhan \= Tidak
\- Subscription Auto Open masih aktif
\- Vercel Toggle \= ON
\- Masih dalam jam operasional

Maka:
\- Bot memastikan ShopeePartner Toggle \= ON.
\- Jika ShopeePartner Toggle \= OFF, bot mengubahnya menjadi ON.

Logika Auto Close:

Jika:
\- Status Penangguhan \= Ya
\- Vercel Toggle \= OFF

Maka:
\- Bot memastikan ShopeePartner Toggle \= OFF.
\- Jika ShopeePartner Toggle \= ON, bot mengubahnya kembali menjadi OFF.

**9\. ADMIN DASHBOARD**

Tim internal FoodMaster dapat:
\- Login sebagai admin.
\- Menambahkan portal.
\- Menambahkan outlet.
\- Mengisi dan mengubah Merchant ID.
\- Mengisi dan mengubah Store ID.
\- Mengatur jam operasional.
\- Membuat dan mengubah password dashboard merchant.
\- Mengaktifkan atau menonaktifkan subscription Auto Open.
\- Mengubah tanggal mulai dan berakhir subscription.
\- Mengubah Vercel Toggle.
\- Mengubah Status Penangguhan menjadi Ya atau Tidak.
\- Menambahkan alasan penangguhan.
\- Melihat seluruh outlet.
\- Melihat status Vercel Toggle.
\- Melihat status ShopeePartner Toggle.
\- Melihat log aktivitas bot.
\- Menghapus atau menonaktifkan outlet.

**10\. DATA MINIMUM SETIAP OUTLET**

Setiap outlet minimal memiliki data:

\- Nama pemilik
\- Nama portal
\- Nama panjang outlet
\- Nama pendek outlet
\- Merchant ID
\- Store ID
\- Hari operasional
\- Jam buka
\- Jam tutup
\- Vercel Toggle
\- ShopeePartner Toggle terakhir
\- Status Penangguhan
\- Alasan penangguhan
\- Tanggal mulai penangguhan
\- Tanggal berakhir penangguhan
\- Paket subscription Auto Open
\- Tanggal mulai subscription
\- Tanggal berakhir subscription
\- Total masa aktif subscription
\- Status subscription
\- Waktu pengecekan terakhir

**11\. SUBSCRIPTION LOGIC**

\- Subscription hanya berlaku untuk fitur Auto Open.
\- Auto Open hanya berjalan jika subscription masih aktif.
\- Masa aktif mengikuti total durasi paket, termasuk bonus.
\- Paket 3 bulan aktif selama 3 bulan.
\- Paket 6 bulan aktif selama 7 bulan.
\- Paket 12 bulan aktif selama 16 bulan.
\- Jika subscription berakhir, fitur Auto Open otomatis dinonaktifkan.
\- Subscription yang berakhir tidak otomatis mengaktifkan Status Penangguhan.
\- Admin dapat memperpanjang masa subscription.
\- Sistem menampilkan tanggal berakhir subscription.
\- Fitur Auto Close tetap dapat berjalan jika Status Penangguhan \= Ya.

**12\. MONITORING DAN LOG**

Sistem menyimpan data log minimal berupa:

\- Waktu pengecekan
\- Nama panjang outlet
\- Nama pendek outlet
\- Store ID
\- Status Penangguhan
\- Status subscription
\- Status Vercel Toggle
\- Status ShopeePartner Toggle sebelum tindakan
\- Tindakan bot
\- Status ShopeePartner Toggle setelah tindakan
\- Status berhasil atau gagal
\- Pesan error jika terjadi kegagalan
\- Admin yang mengaktifkan atau mencabut penangguhan
\- Alasan penangguhan

Contoh log:

\- Open Store berhasil
\- Close Store berhasil
\- Outlet sudah terbuka
\- Outlet sudah tertutup
\- Outlet dibuka kembali karena Vercel Toggle ON
\- Outlet ditutup kembali karena Vercel Toggle OFF
\- Outlet ditangguhkan oleh Admin
\- Penangguhan outlet dicabut
\- Gagal membuka outlet
\- Gagal menutup outlet
\- Akses akun tidak valid
\- Nama portal tidak ditemukan
\- Store ID tidak ditemukan

**13\. SECURITY**

\- Dashboard wajib dilindungi dengan password.
\- Merchant hanya dapat mengakses data miliknya sendiri.
\- Merchant tidak dapat mengubah Status Penangguhan.
\- Status Penangguhan hanya dapat diatur oleh Admin FoodMaster.
\- Admin dapat mengakses seluruh data.
\- Password tidak boleh disimpan dalam bentuk plain text.
\- Akses ShopeePartner harus disimpan dengan aman.
\- Setiap perubahan Status Penangguhan wajib tercatat dalam log.
\- Aktivitas penting harus mencatat waktu dan identitas admin.

**14\. NOTIFIKASI**

Pada versi awal, notifikasi dapat dikirim kepada admin jika:

\- Bot gagal membuka outlet.
\- Bot gagal menutup outlet.
\- Outlet kembali terbuka ketika Vercel Toggle OFF.
\- Akses Staff sudah tidak aktif.
\- Nama portal tidak ditemukan.
\- Store ID tidak ditemukan.
\- Automation gagal beberapa kali.
\- Subscription merchant akan berakhir.
\- Subscription merchant sudah berakhir.

Notifikasi dapat dikirim melalui WhatsApp, Discord, atau channel internal FoodMaster.

**15\. KRITERIA KEBERHASILAN MVP**

MVP dinyatakan berhasil jika:

\- Admin dapat menambahkan portal dan outlet.
\- Merchant dapat login ke dashboard dengan password tertentu.
\- Merchant dapat menggunakan Vercel Toggle ON/OFF.
\- Bot dapat membaca Vercel Toggle sebagai source of truth.
\- Bot dapat membaca status aktual ShopeePartner Toggle.
\- Bot dapat membuka outlet ketika Vercel Toggle ON.
\- Bot dapat membuka kembali outlet yang ditutup sementara oleh ShopeeFood.
\- Bot dapat menutup outlet ketika Vercel Toggle OFF.
\- Bot dapat menutup kembali outlet yang dibuka melalui ShopeePartner ketika Vercel Toggle OFF.
\- Admin dapat mengubah Status Penangguhan menjadi Ya atau Tidak.
\- Auto Close tetap berjalan selama Status Penangguhan \= Ya.
\- Merchant tidak dapat mengubah Status Penangguhan.
\- Auto Open tidak berjalan jika subscription sudah berakhir.
\- Subscription yang berakhir tidak otomatis menjadi penangguhan.
\- Masa aktif subscription sesuai paket dan bonus.
\- Seluruh tindakan bot tercatat dalam log.

**16\. URUTAN PRIORITAS SISTEM**

Urutan prioritas pengambilan keputusan bot:

1\. Status Penangguhan
2\. Status subscription Auto Open
3\. Vercel Toggle sebagai source of truth
4\. Jam operasional
5\. ShopeePartner Toggle sebagai status aktual outlet

**17\. FUTURE DEVELOPMENT**

Fitur lanjutan yang dapat dikembangkan:

\- Notifikasi WhatsApp kepada merchant.
\- Pengaturan jam operasional langsung oleh merchant.
\- Dashboard statistik uptime outlet.
\- Pembayaran dan perpanjangan otomatis.
\- Multi-user dalam satu merchant.
\- Pengaturan hari libur atau jadwal khusus.
\- Deteksi otomatis jika akses Staff dicabut.
\- Health monitoring untuk seluruh bot.
\- Riwayat penangguhan merchant.
\- Persetujuan berjenjang sebelum Status Penangguhan diaktifkan.
