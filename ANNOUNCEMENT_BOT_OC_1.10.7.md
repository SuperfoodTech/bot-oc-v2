# Pengumuman Rilis FoodMaster Bot-OC

## Rilis peningkatan algoritma bot dan pengalaman dashboard

FoodMaster Bot-OC kini berjalan dengan alur patroli bot yang lebih merchant-aware, kontrol outlet yang lebih praktis, dan pengalaman dashboard admin maupun mitra yang lebih rapi untuk penggunaan harian.

Selain peningkatan perilaku bot, sistem sekarang juga lebih mudah dipantau dan dioperasikan karena status, jadwal, dan aksi massal sudah tampil lebih jelas di berbagai tampilan.

**Tanggal rilis:** 1 September 2026  
**Nama rilis:** Bot-OC v1.10.7  
**Jenis rilis:** Feature Highlight and Operations Update

## Apa yang baru?

- Bot patroli sekarang memakai pendekatan merchant-aware, sehingga antrean kerja dibangun per akun Shopee dan portal merchant, bukan sekadar per outlet.
- Scheduler memprioritaskan outlet yang benar-benar butuh aksi, misalnya saat Shopee menutup outlet di tengah jadwal aktif atau saat pause perlu dijaga lintas sesi.
- Worker bot memproses beberapa outlet dalam merchant yang sama dalam satu context Shopee, sehingga switch merchant menjadi lebih efisien dan patroli lebih cepat.
- Dashboard mitra sekarang memiliki tombol langsung ke halaman outlet ShopeeFood melalui `Store ID`, sehingga pengecekan manual bisa dilakukan lebih cepat.
- Dashboard admin mendukung mode `Pilih beberapa` untuk membuka atau menutup beberapa outlet sekaligus.
- Dashboard Virtual Brand juga mendukung bulk action untuk beberapa brand sekaligus.
- UI/UX dashboard admin dan mitra ditingkatkan dengan layout mobile yang lebih rapi, detail outlet yang lebih mudah dibaca, scroll area yang lebih stabil, dan feedback toast yang lebih konsisten.
- Sinkronisasi status Virtual Brand diperkuat agar perubahan toggle dashboard lebih cepat terbaca oleh worker patroli.

## Sorotan algoritma bot

Perubahan paling penting ada pada cara bot menentukan giliran patroli.

Sebelumnya, biaya switch merchant bisa membuat outlet penting ikut menunggu. Sekarang, bot:

- mengelompokkan outlet berdasarkan `(username Shopee, nama_portal)`,
- menghitung prioritas dari kondisi outlet di dalam grup tersebut,
- memilih merchant group paling urgent lebih dulu,
- menghitung ulang antrean setelah satu group selesai diproses.

Hasilnya, kasus seperti random close dari Shopee saat outlet seharusnya buka bisa naik prioritas lebih cepat tanpa harus menunggu satu global cycle penuh selesai.

## Sorotan dashboard admin dan mitra

### Dashboard mitra

Mitra sekarang mendapat pengalaman yang lebih praktis untuk operasional:

- kartu outlet menampilkan status yang lebih jelas,
- jadwal outlet bisa dibuka langsung dari card,
- ada shortcut `Lihat outlet di ShopeeFood`,
- riwayat aktivitas dan informasi akun ditampilkan dengan hierarki yang lebih rapi,
- feedback error dan sukses lebih konsisten di mobile.

### Dashboard admin

Admin sekarang lebih mudah menangani banyak outlet sekaligus:

- tersedia quick action `Pilih beberapa`,
- outlet terpilih bisa dibuka atau ditutup massal,
- tampilan mobile admin diselaraskan dengan struktur desktop terbaru,
- aksi sensitif seperti hapus outlet dipindahkan ke area detail agar lebih aman,
- tab Logs dan Settings memakai scroll internal yang lebih stabil.

### Virtual Brand

Flow Virtual Brand juga lebih siap dipakai operasional:

- toggle brand dari dashboard lebih konsisten terhadap state bot,
- status pending tidak mudah tertinggal,
- tersedia bulk selection untuk beberapa brand,
- daftar brand dan detail store lebih mudah dibaca di dashboard admin.

## Fitur penting yang kini terasa di operasional

- Bot lebih hemat switch merchant karena memproses outlet per group merchant.
- Outlet yang mismatch antara target internal dan status live Shopee lebih cepat diangkat ke prioritas tinggi.
- Pause yang melewati break multi-schedule tetap dijaga agar outlet tidak terbuka lagi sebelum waktunya.
- Dashboard memberi jalur lebih cepat untuk aksi massal dan pengecekan manual ke ShopeeFood.
- Tampilan mobile admin, mitra, dan Virtual Brand lebih siap dipakai tanpa terasa seperti versi desktop yang dipaksa mengecil.

## Dokumentasi pendukung

Sebagai pelengkap dari perilaku sistem yang sekarang aktif, dokumentasi operasional juga sudah disiapkan di folder `dokumen project`, termasuk:

- SOP dan runbook
- dokumentasi API
- test report
- dokumentasi pengguna
- dokumentasi sistem patroli bot

## Catatan penting

- Bot masih tetap bergantung pada session Shopee, jaringan, dan validitas data akun di database.
- Merchant-aware scheduling yang aktif sekarang sudah jauh lebih relevan untuk produksi, tetapi merchant group yang sangat besar masih bisa memakan waktu lebih lama dibanding group kecil.
- Beberapa area seperti keamanan kredensial dan konsistensi akun VB masih tetap perlu perhatian lanjutan.

## Penutup

Rilis ini menandai Bot-OC sebagai sistem yang tidak hanya punya dashboard yang lebih matang, tetapi juga logika patroli yang lebih sadar konteks merchant, lebih efisien, dan lebih dekat dengan kebutuhan operasional outlet sehari-hari.
