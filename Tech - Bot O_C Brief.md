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

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAkUAAADLCAYAAABgW+dAAAAqp0lEQVR4Xu3dB5BUVd7+ccyp0NJSX7R0d5VSt0xlKlFY47qIuvi6YABkcVcXE7oGXMEAKGLCnAUVwx9dFQUTqyhmkCBhGHIacs45yu/Pc3zP3dNnOgwDw/T0fD9Vv5q+sXtuX+59+pzTQ41Zs2bZzJkzM9aMGTOS6t69u3311Vfu8fTp0ymKoiiKoiq9wqwSVpxpwlL+mT17dkrViFcKw1D8pBRFURRFUVWpcoWjtKEoUwiaNm0aRVEURVFUlas402QKSSmhKF0ginesmjp1akpNmTKFoiiKoiiq0irOJnF2SReO0gUjdafViAPRloSgkpISiqIoiqKoSqs4m8TZJVM4SjfuqEYYhgAAAApZunCUEop8qxAAAEAhy9Rq5EJR2FUGAABQyMIutbgrzYUiraB+OQAAgEIWjzUKg1ENP4B60qRJ8XYAAAAFxQ/OjoORC0X+W2SEIgAAUOgmT55cKhj51qIkFE2YMCHeDgAAoKCoESj8Kn9KKPKtRIQiAABQ6JR34mBUKhSNHz8+3g4AAKCghKHIByPfWlRDfWtaOG7cuHg7AACAguJDUTi2KAlFWjBx4kRCEQAAKHgKRco9PhgpFGnAdUooGjt2bLwdAABAQdFwoayhSKmJUAQAAAqdQlHchUYoAgAAeWf27NnxrES2ZWWVKRRpXFENNSFp4ZgxY+LtAAAAtquhQ4faSy+95H6GFIg++eSTlHnl4UOR8o9CkYpQBAAA8pIPRp4CUTi9NQhFAACgSlEwUvlAtC1aiSRTKFIRigAAQF5SGNqWgUj0J4gyhqLjjz/efve739lvf/vbeDsAAIBK4ccQZRpjVF5hKPKDrZNQpEBEKAIAAPkiHkMUjzHaGjlD0f3332/9+/ePtwMAANiuMo0h8mOMtlbOUHTiiSfaZ599Fm+3zbknrFHDrr322niRbdy40QYOHOhqWzvssMPc8/radddd7YwzznAHpLLpzddrSueWW25Jed1x1a1bN96klJEjR7pjunz58njRNvfNN9/YKaeckry+HXfc0a6//nqbM2dOvGpe2Z7HCACQXbbg4wdeb42coWh7dZ89/PDD7ma52267lboBrVixwi3bYYcdUuZvCz4UnX766Xbqqafafvvt56b32GMP69mzZ7z6djV37lw79NBD49nOfffd55ap9txzzyTQ+XmXXnppvEkpp512mtuuIsJm6IcffrCdd97ZPdfFF19sjRo1spo1a7rp4447Ll49r2yvYwQAqHzpQpH/rz5qHHPMMdslFP3yyy/ueZo0aeJuQG+99VbK8u0RikKLFy92LRk77bSTOyD5Tl2c+h0aN24cL8pqe93wL7nkEvc8jzzySDJvxowZtssuu5Q69vlmex0jAEDlyxqKtPDTTz91YaUiqSVBNx6NXdLPs846K1nWpUsXu+CCC9x8VatWrdz8J554who2bJisJwpTft6XX37pHr///vuu20YtFWvXrk1ZX9KFImnatKmb/7e//c1Na18tW7ZMWUfzwtegx6NHj7bXXnstaeFRU17r1q3d86glR92DOrieupX+/Oc/2z777GO77767vf3228myRYsWlfod00kXivzx+e6775J5/vj06NHD/fQtTOpq07Q/Zs8//3yyzbBhw9y8du3auWl1eWlarVg33nij+z2bN2+etbuxdu3a7nnat2+fMv+DDz6wjh07psxT65xakc4880z3O6jrVPxr+/e//+2202vXtJ531apV7viefPLJbpsFCxYk+9P2jz76qGsJVDj76KOPkmX+GBUXF9vrr7/u1jnvvPOS5lmdj/ExklzvqdbTeaftde75806/27nnnmt777231alTp1T4BwBUrqyhqH79+u4PGVXk3ylatmyZu7Go5K677nI3oQ4dOiTrpGspuuqqq0qFGd10/Tzd5PRYLT4jRoxwAWPTpk0p60umUKRt/Pbr1693j7VuyAe1cFrr33zzze4g6saoeUcddVRyY/QB79tvv022CUfNh8+TbUxRKF0o8sfn3XffTeb549O5c2c3HbeC+GN2ww03JNv07dvXzWvQoIGbPvLII920WvZmzpzpQofCouZdeOGFyXYhtQodfvjhyfHS73frrbe6ffv3RP+/no6dWidl9erVybFSEArfT71evZ/qatU83wX3448/ummdS9pvt27d3HSLFi1s3bp17i+SHnTQQW4fen/8MTrggAPcf/YnCqeap/dO4mNU1vdUz6Fgp/NIr8UHQx96030AAABUrqyhSDc+3eAHDx4cb7fNvPnmm+7mcOWVV7ppfUrXdK1atZJWgq0JRT5sZZIpFOlgaL5K3Wn6WZZQpHFJ/kavA6kbtX56GlOj9fxNV4/V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ZzfccEMyHdJ9avTo0SnzdN157rnncp6boddeey2elVYhvocVqVJDkbrIykLraYxROnfddVfKxeSNN95wPzt27Gg33XSTezx79mzbcccdbeXKlcl68uSTT9rMmTPt0UcftZEjR9q0adPs/vvvt1tuuSVZZ926dfbKK6/Y66+/7i6WMmTIEPv666/ttttuswcffDD5NNmzZ0+3n3/84x928MEH5wx8KJuyfLovSyvAO++8kzyeMWOG+3nWWWelBJMzzjgjeSzz5s1z7/2oUaPs7rvvduF6wIABdscdd9i9997rzh9RV+8jjzxirVu3TrbV+aCwdvPNN9urr76aBK7evXunnCcPP/xwsg3KL9f77+Va74orrkiZ/uqrr5LHRUVFds8999jw4cOTebqZ6X2+9dZb3XvuDRo0yP71r3/Ztddea88//7yb58+Jbt26ufMiPCd0XVGr+AsvvGDXX3+9O8c8XatmzZpljz32mPXp0yeZr6EGug7pJl1cXOw+CIYUihTwQp9++mnyWNe8Bx54wF335syZ4+bp/P7hhx/ctU0tsE899VSyfiHQ2CGFHoWhyc3PcuEnrNUTfw0smVqSRO/bXnvt5R4PHDjQBaRrrrnG3n77bfce7rTTTu7aofdH73OrVq3s448/dusfdthhSSjS8e3cubN7D2rUqOHeB50f//nPf1upli1bljwO6ZoSC88ff46G76HuWzqf/b0LpVVqKPJjiHLRehp8nY2Ck240Z555pptu3ry5vfTSS8nyPffc08aOHZtMi07qBg0a2Pvvv28HHnig1a9f390AdQFavny5a50677zz7Pbbb3cn/F/+8he3XZcuXeyoo45yJ3nDhg3dpwRRS5GOly5mOvHLGvqQXVnHDOVaTxf7tm3buvfJB2l9itbNxItvIApDmqfWgk8++cSOP/54u+SSS+zDDz9058S5557rbiZ6v3Vz/Oijj+yZZ55x2zZp0sROPvlke++999z58uKLL7r5+gQZnifpLm7Ycrnefy/XegrPHTp0cOdL+G9YNxS1Buj9/M1vfmM//fSTm3/QQQe591fhWq2Q9913n5uv64s+zesGV7duXTfPnxNPP/202094TuicbNy4sQtlCi46j/wHMe1LN169tl133dVGjBjh5rdp08YFId1YDz30UHfdCykU1axZ030I8KVrnOhDoq577du3d63p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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAloAAACXCAYAAADNsvWpAAAjk0lEQVR4Xu3dB5AVReLHcc8cSi2v1FKrtE6t0ytTmf5iODFgTocggsBfCQpiBAzoKQaCiuCB6BkIovwNZJCggCIeKKKn5LgLu+S0S9oMG/q/v157nDf7dt+GGXbZ/X6quvZNz7y3b2eamd/r7jccYAAAABCJA4IVAAAACAdBCwAAICIELQAAgIgQtAAAACJC0AIAAIgIQQsAACAiBC0AAICIELQAAAAiQtACAAAotmnTpmBVjETr4yFoAQAAFPvtt9/M+++/b3/6KWCpfuLEiTH1FUHQAgAA+F0wbFUnZAlBCwAAwMeFreqGLCFoAQAABLiwVZ2QJQQtAACAANebFZyvVVkELQAAAB9/yKpu2CJoAQAA/C44L6u6YYughcisXbvWLFq0yOzevTu4CgCAWqe8OVlVDVyhB601a9aYAw44wJYOHToEV5uCggIzd+7cYHVoTj/9dO/3u3L11Vebrl27muTk5ODmNUaJWe/tmGOOCa6ynnzyyVJ/R7BceeWVwaeVsnjxYru/MzIygqsi891335lLL73Ue58HHnigefjhh83mzZuDm9Zq2nf7cr8BAGpWohCl9ZW9aWnoQev111/3LrCHHXZYcLXJzMy066LigtaZZ55prrjiCnPZZZd57+eII44w48aNCz6lRmzZssWceuqp5sILLwyusl555RW7XuXII4+07//QQw/16lTuueee4NNKufzyy+1zowy3frNmzTIHH3yw/Z133XWXadKkiTn66KPt8vnnn2927doVfEqtpX23r/YbAKBuCjXxFBYWmr/85S+2B6NFixZxA9W+ClqjR4/26nbs2GFefPFF+74OOuggs3r1at8zar9XX33V/k1NmzYNrkpoXwetxo0b29/3xhtveHXr1683hxxyiK1Xt+v+gqAFAKiuUBOPejN0MdXF9scffywVqD788ENz66232vo777zTPProo7b+rbfessvff/+9t+3w4cNtnQtM06dPt8t6XQ1LqdckLy/P296JF7Sc++67z65r06aNXd6wYYN56KGHYrbJzc21v0dF3HtbunSpGTp0qO1JatSoke06fOqpp+zvU0/TySefbIdKNXTqaAjtjjvuMMcee6w5/PDDzWeffeat2759u33dli1benVlKSto6b3595m4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Csxrr71mzj33XNO7d2+7vC888sgjZtCgQfYx7SlCRUVeaMpJXmp7rRyFqN0/zTC7Zk01ezZvsHWuZ0vbuufFmySv9tO2bVtz7LHHmj/96U+mZcuWttd+X/C3nSjMnj3bHHfccTF1kydPNmeffXZMXXnUpo855phgdZ2ic47OPeWpyPlp4MCB5vbbb4+p+9vf/haz3L17d9OpU6eYOj9dJ4N0LnvnnXfK/d1BN9xwgxk6dGiwOq76cIzDFkrQ0tBgRWnb7du3B6s933zzjUlKSrKfCK699lrz/PPP2/olS5aYI4880j73wQcf9MJP1DZu3Gjmz59vH3///ffmqqv+OGEjGmlpacGquNRFn2jbuXPnmtNOO82sX7/entQ++eQTWz948GAbvtTOFOyjvID5LV682KxZs8Y+pj1FR98udIFp67D+dshQMv4726xufY0NVa442kbbuufpNYIUym+77TazZ88es3XrVhtCevToEdwsEv62EwUFLQVIv0mTJpmzzjorpq48Cp3ffvttsLpO0TlH555EEp2fdF05/PDDvQ95CkYKuhs2lIR/0flhzJgx3nKQOh6C1DYPOOCASn0AaNSokRkyZEiwOq76cIzDFkrQqswB1bZr16wNVntcsJKPP/7Y3HXXXfaxTmaPPfaYfbxp0yZz4IEHxvR2yb/+9S/bSPv06WOefvppe2Jau3atefLJJ83PP//sbaeGqAut6l0Px6+//mpmzJhhg16XLl3sCVX0GuPGjbM/FfBOOeUU8/rrr3uvhfAp/FSEG0IsT5s2bcznn39uHyts/fTTT/bxNddc4/Um6UR29dVXe89xdCFVwP/nP/9pXn31VduLquerbflPhvrw8MYbb5innnrKTJkyxdapzegT7UcffWQef/xxexLTCVXr1daC7akiPcKoON22wQWmNV1b2h4r9WQFQ5brxRI7hFi8rRe0dOuHgObNm8cEK50vBgwY4C0vWLDAvPDCC96HM1HvgtqCjrPahZ/OS88884zp0KGD2bt3r62L13bEtR3RFIx///vf5uGHH475XToH6sNh3759zbRp07x6zZlVO9e5TT0pGh0IqkjQ6tmzp32v+vewefNmW6d/E7/99ps9Z2q4rH///t72dZHOOYl63CXR+Unng6OOOso7fvpQ2L59e/PZZ5/ZZR3jgw46yJ6HdOzUFh599FHz5Zdfeq/hgpb2+5tvvmmPg46RgpaOkdrLV1995W2/e/du89Zbb3nLTllBy9/OdN4T/zH2Xzd1/BlOjy+UoOUmvleEtk1amRSsjqEwpgtRw4YNzdixY21d69atzfvvv+9to96t5cuXe8uiRnvLLbeYUaNG2bB14oknmptuusmefA477DCTkZFhhy3VTdq1a1fbLX733Xfb53744Yf202nnzp1tQ77zzjttvRs6VC+bGpoadrwGifAk6pb3S7StgowuBDqG6rVynx71yXHRokX2sdpa8AIjClkaGpo4caK5//77zQUXXGAaN25s2+T1119vt9HFRm1CF9MJEyaYK664wta3aNHCXHLJJfYiPHLkSNu23nvvPTsMoPcRbE+V+bCCxHSPLBeYXK+VhguDIUslbXxJL6do2T1PrxGk0H7ooYeal19+udQx0wVHQz863upFnTNnjq0/+eST7fF3vaivvPKKrddFSucsDdnoYqhwJPHajri2I02bNrWhT0FIvSLuA6NeTz237n0uXLjQ1nfr1s2OEChg6YKs82mQgtbRRx9tP5C4MmzYMC9o6YPtSy+9ZAOcpm/ceuuttl4X3UsvvdQGSQ0r6TXqskTnHL9E2957773mgw8+sI+1/3S9adeunV2eOXOm7W0XtRtd11R07nIfGHX+0ChPgwYNTL9+/ew1Tq+noKXzja5rGnJ29AFR186gsoKWv529/fbbtp35j7H/uqlrZrNmzQKvAAklaFVWosb36aef2hONTlpuWx1w/aN3FKLmzZvnLYtOMj/++KO3rMbgehhOOukks2zZMjtfR0HLOf/88+2nADWYK6+80qvXtuKfo8VQz76RqH34lbetQr0+ESr8fPfdd+ayyy6zcx5EwVthR5KTk+1FKUhBy/U0LV261L6WGwpwcxTU2+Xv4VTw0slIF0tdlBxdZB944IGYiyXtKTrxgpbmZAVDlg1ao/64wCQKWjJr1iwbNNRmdG7QvFNR+/rhhx/sY/VKKZSLgpbrVdXQn56nyfS6WCrEO+4CG6/tiGs7atcKS673QK/n3oPOgW5YRx8SdM7ctm2bbe/+ea1lBS2NFOji7crxxx/vBS31lPm31TlVFLTc6AJBK1aibRWKWrVqZR+rl13njxNOOMEeY/VM6fwi6ikVdRSo88BNgdAx0gdA9X46/qHD6gStYDvTMVY7CwYtd93UNVPt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>