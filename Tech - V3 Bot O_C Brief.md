**Database**  
[**https://docs.google.com/spreadsheets/d/10osh4rI4q\_mv6fBe9NurXRztRrGa85L01Bwned6m0Qs/edit?usp=sharing**](https://docs.google.com/spreadsheets/d/10osh4rI4q_mv6fBe9NurXRztRrGa85L01Bwned6m0Qs/edit?usp=sharing) 

**Status:** Final Requirement Brief  
**Versi:** V3.0 — Replacement Brief  
**Tanggal:** 26 Agustus 2026  
**Product Owner:** FoodMaster

---

# **1\. TUJUAN PRODUK**

Auto Open/Close Bot ShopeeFood adalah sistem yang membantu menjaga status buka/tutup outlet ShopeeFood berdasarkan:

1. status layanan;  
2. jam operasional outlet di Shopee;  
3. toggle yang dikendalikan melalui Dashboard;  
4. pilihan OFF sementara atau manual;  
5. aksi otomatis Bot.

Produk digunakan dalam dua konteks:

### **A. Agency**

Layanan berlangganan yang diberikan FoodMaster kepada merchant eksternal.

Merchant memperoleh landing page/dashboard khusus untuk mengendalikan outlet ShopeeFood miliknya.

### **B. Virtual Brand / VB**

Sistem yang digunakan secara internal oleh FoodMaster untuk mengendalikan sejumlah Virtual Brand.

Pada VB, satu grup dapat terdiri dari banyak Store ID yang berasal dari beberapa outlet.

---

# **2\. PRINSIP UTAMA SISTEM**

Sistem menggunakan tiga sumber informasi dengan fungsi berbeda:

### **Google Sheet**

Sebagai **master data**.

Semua perubahan data outlet dilakukan dari Google Sheet.

Dashboard tidak digunakan untuk mengedit master data.

### **Dashboard**

Sebagai **control layer / desired state**.

Dashboard menentukan apakah outlet seharusnya berada pada kondisi ON atau OFF selama sistem memperbolehkannya.

### **ShopeePartner / ShopeeFood**

Sebagai sumber:

* jam operasional outlet;  
* status aktual outlet;  
* eksekusi buka/tutup outlet.

---

# **3\. HIERARKI BUSINESS RULE**

Sistem harus membedakan beberapa jenis kontrol.

Urutan evaluasi secara konseptual adalah:

### **1\. Status master data**

Apakah row **Aktif** atau **Nonaktif**.

Jika Nonaktif, row tidak menjadi bagian dari kontrol operasional Bot.

### **2\. Eligibility layanan**

Khusus Agency, tanggal layanan harus masih berlaku.

VB tidak menggunakan tanggal mulai atau tanggal berakhir layanan.

### **3\. Jam operasional ShopeeFood**

Bot hanya boleh menjaga outlet terbuka ketika outlet sedang berada dalam jam operasional Shopee.

### **4\. OFF override**

Jika terdapat OFF sementara/manual yang masih aktif, outlet harus tetap tertutup walaupun telah memasuki jam operasional.

### **5\. Toggle Dashboard**

Jika tidak ada OFF override dan outlet sedang berada dalam jam operasional, toggle Dashboard menentukan desired state outlet.

---

# **4\. MASTER DATA GOOGLE SHEET**

Google Sheet tetap menjadi **source of truth master data**.

Setiap perubahan master data wajib dilakukan melalui Google Sheet dan kemudian dilakukan **Fetch dari Dashboard**.

Fetch tetap merupakan action manual.

---

# **5\. STRUKTUR GOOGLE SHEET — AGENCY**

Struktur Agency saat ini:

| Kolom | Field | Fungsi |
| :---- | :---- | :---- |
| A | Nama Pemilik | Identifier pemilik/merchant |
| B | Status | Aktif / Nonaktif |
| C | Paket | Paket layanan |
| D | Tanggal Mulai Layanan | Awal masa aktif layanan |
| E | Tanggal Berakhir Layanan | Akhir masa aktif layanan |
| F | Akses Username | Credential operasional |
| G | Akses Kata Sandi | Credential operasional |
| H | Merchant Name | Nama merchant/portal terkait outlet |
| I | Store ID | Identifier utama outlet ShopeeFood |
| J | Nama Panjang Outlet | Nama outlet yang ditampilkan |
| K | Vercel Kata Sandi | Password akses landing page merchant |

### **Business Rule Agency**

**1 row \= 1 Store ID.**

Satu pemilik dapat mempunyai banyak row karena mempunyai banyak outlet.

Contoh:

**Pemilik A**

* Outlet 1  
* Outlet 2  
* Outlet 3  
* Outlet 4

semuanya dapat ditampilkan dalam **satu landing page milik Pemilik A**.

Store ID adalah identifier utama masing-masing outlet.

---

# **6\. STRUKTUR GOOGLE SHEET — VIRTUAL BRAND**

Struktur VB saat ini menggunakan format horizontal.

### **Kolom utama**

| Kolom | Field |
| :---- | :---- |
| A | Nama Outlet Asli |
| B | Status |
| C–D | Portal SuperFood Store ID |
| E–F | Portal WonderFood Store ID |
| G–H | Portal Lokarasa Store ID |
| I–L | Portal Gurame Bakar, Do Eat Store ID |

Struktur dapat berkembang apabila di masa depan terdapat portal tambahan.

### **Business Rule VB**

**1 row \= 1 grup VB.**

Nama pada **Kolom A — Nama Outlet Asli** adalah identifier grup.

Contoh:

**Katsunami**

dapat mempunyai:

* SuperFood Store ID;  
* WonderFood Store ID;  
* Lokarasa Store ID;  
* Do Eat Store ID;  
* dan Store ID lain pada row yang sama.

Semua Store ID valid pada row tersebut merupakan anggota satu grup.

### **Cell kosong**

Tidak semua grup harus mempunyai Store ID pada semua portal.

Jika suatu cell Store ID kosong:

* cell tersebut dilewati;  
* tidak dianggap error;  
* tidak menghalangi Store ID lain dalam grup untuk diproses.

### **Status VB**

VB tetap menggunakan **Status Aktif / Nonaktif** pada Kolom B.

Namun VB **tidak mempunyai Tanggal Mulai Layanan maupun Tanggal Berakhir Layanan**.

Status Aktif/Nonaktif merupakan master switch apakah row/grup tersebut masuk ke proses operasional.

---

# **7\. PERBEDAAN AGENCY DAN VB**

| Aspek | Agency | VB |
| :---- | :---- | :---- |
| Unit dasar | Store ID | Grup berdasarkan Kolom A |
| Satu toggle | 1 Store ID | Seluruh Store ID dalam grup |
| Merchant eksternal | Ya | Tidak |
| Landing page merchant | Ya | Tidak |
| Password merchant | Ya | Tidak |
| Subscription | Ya | Tidak |
| Tanggal mulai/akhir | Ya | Tidak |
| Digunakan oleh | Merchant \+ Admin | Internal FoodMaster |
| Bulk control | Per outlet | Per grup |

---

# **8\. STATUS AKTIF / NONAKTIF**

Status pada Google Sheet berbeda dengan toggle ON/OFF.

## **Status \= Aktif**

Menentukan bahwa data tersebut boleh masuk ke sistem operasional Bot.

## **Status \= Nonaktif**

Menentukan bahwa data tersebut tidak diproses sebagai outlet aktif oleh Bot.

### **Penting**

Status Aktif/Nonaktif adalah level master.

Sedangkan:

* tanggal layanan;  
* toggle ON/OFF;  
* OFF duration;

adalah level operasional setelah row dinyatakan Aktif.

---

# **9\. SUBSCRIPTION — KHUSUS AGENCY**

Agency mempunyai:

* Paket;  
* Tanggal Mulai Layanan;  
* Tanggal Berakhir Layanan.

Auto Open dapat bekerja jika:

1. Status row \= Aktif; dan  
2. tanggal saat ini masih berada dalam masa layanan.

### **Paket**

Field Paket merupakan informasi paket layanan.

### **Tanggal layanan**

Tanggal Mulai dan Tanggal Berakhir menjadi acuan aktual apakah layanan masih berlaku.

---

# **10\. JIKA SUBSCRIPTION AGENCY BERAKHIR**

Ketika tanggal layanan sudah berakhir:

### **Bot**

Bot **berhenti bekerja** terhadap outlet tersebut.

Bot tidak:

* membuka outlet;  
* menutup outlet;  
* mengubah status outlet terakhir.

Status outlet di ShopeeFood dibiarkan apa adanya.

### **Dashboard Merchant**

Outlet tetap dapat ditampilkan tetapi kontrolnya terkunci.

Toggle menjadi **disabled**.

Tampilkan warning:

> **Layanan berakhir**  
> Auto Open tidak lagi berjalan. Hubungi FoodMaster untuk memperpanjang layanan.

Merchant tidak dapat mengubah tanggal layanan.

---

# **11\. PERPANJANGAN SUBSCRIPTION**

Perpanjangan dilakukan oleh Admin FoodMaster melalui Google Sheet.

Admin:

1. mengubah Tanggal Berakhir Layanan;  
2. melakukan Fetch dari Dashboard.

Jika tanggal layanan kembali valid:

* layanan otomatis aktif kembali;  
* merchant tidak perlu melakukan aktivasi tambahan.

Jika pada saat aktivasi outlet sedang berada dalam jam operasional, kontrol kembali aktif sesuai business rule.

Jika sedang berada di luar jam operasional, toggle mengikuti aturan outside operating hours dan akan kembali ON pada jadwal operasional berikutnya.

---

# **12\. LANDING PAGE AGENCY**

Setiap **pemilik** mempunyai satu landing page khusus.

Satu landing page dapat berisi banyak outlet milik pemilik tersebut.

### **URL**

Setiap pemilik memperoleh **unique landing page URL**.

Contoh konseptual:

`foodmaster.com/bot/[unique-owner-link]`

Detail URL ditentukan tim Tech.

### **Login**

Login merchant hanya menggunakan:

**Password**

Tidak menggunakan username.

### **Password**

Password:

* dibuat oleh Admin FoodMaster;  
* dikelola Admin FoodMaster;  
* merchant tidak dapat mengganti password sendiri;  
* tidak wajib unik antar merchant.

Dua merchant boleh mempunyai password yang sama karena setiap merchant sudah mempunyai URL landing page yang berbeda.

---

# **13\. HAK AKSES MERCHANT**

Merchant hanya dapat melihat outlet miliknya.

Merchant dapat:

* melihat outlet;  
* melihat Store ID;  
* melihat Merchant Name;  
* melihat jam operasional;  
* melihat status buka/tutup;  
* mengubah toggle;  
* memilih durasi OFF;  
* melihat waktu outlet akan buka kembali;  
* melihat activity log;  
* Membuka link CTA menuju outlet ShopeeFood.

Merchant tidak dapat:

* mengubah Store ID;  
* mengubah Nama Pemilik;  
* mengubah Paket;  
* mengubah tanggal layanan;  
* mengubah credential;  
* mengubah master data;  
* mengganti password landing page.

---

# **14\. ADMIN FOODMASTER**

Admin dapat mengendalikan outlet Agency dari Admin Dashboard.

Admin dan merchant mempunyai **otoritas toggle yang setara**.

Artinya:

* merchant dapat mematikan outlet;  
* Admin dapat mematikan outlet;  
* merchant dapat menyalakan kembali outlet;  
* Admin dapat menyalakan kembali outlet.

Tidak ada Admin Lock khusus.

### **Prinsip**

**Latest valid action wins.**

Jika Admin melakukan OFF dan kemudian merchant melakukan ON, maka ON merchant menjadi desired state terbaru.

Sebaliknya juga berlaku.

Semua perubahan dicatat di log.

---

# **15\. JAM OPERASIONAL**

Jam operasional tidak diatur melalui Google Sheet atau Dashboard.

Jam operasional berasal dari ShopeePartner/ShopeeFood.

Jam harus ditampilkan pada:

* Admin Agency;  
* merchant landing page Agency;  
* dashboard VB.

---

# **16\. FORMAT JAM OPERASIONAL**

Jam operasional ditampilkan secara sederhana per hari.

Jika suatu outlet mempunyai lebih dari satu slot:

Contoh sumber Shopee:

* 06:00–10:00  
* 12:00–18:00

Dashboard cukup menampilkan:

**Senin**  
06:00–10:00, 12:00–18:00

Tidak perlu membuat tampilan yang terlalu teknis.

---

# **17\. TIMEZONE**

Semua perhitungan:

* jam operasional;  
* OFF duration;  
* waktu auto resume;  
* logs;

menggunakan **zona waktu outlet**.

Contoh:

* WIB;  
* WITA;  
* WIT;

sesuai lokasi outlet.

---

# **18\. CORE LOGIC — DALAM JAM OPERASIONAL**

Selama outlet berada dalam jam operasional, **Dashboard menjadi control authority utama**.

## **Toggle ON**

ON berarti:

> **Pastikan outlet tetap buka selama jam operasional.**

Jika toggle ON dan outlet di ShopeeFood sedang tertutup, Bot harus melakukan tindakan untuk membuka outlet.

Jika sudah buka, tidak diperlukan perubahan.

Tidak perlu memberi warning kepada user mengenai perbedaan sementara antara toggle dan status Shopee karena Bot memang bertugas melakukan sinkronisasi tersebut.

---

# **19\. CORE LOGIC — TOGGLE OFF**

Saat user ingin mengubah ON → OFF, outlet **tidak langsung dimatikan**.

Sistem wajib terlebih dahulu menampilkan pilihan durasi OFF.

Pilihan:

1. **30 menit**  
2. **60 menit**  
3. **Sepanjang hari**  
4. **Sampai waktu tertentu**  
5. **Hingga dinyalakan kembali**

Setelah merchant/Admin memilih opsi dan mengkonfirmasi:

* toggle berubah OFF;  
* Bot menutup outlet;  
* Bot mempertahankan outlet tetap tertutup selama OFF masih berlaku.

---

# **20\. OFF 30 MENIT / 60 MENIT**

Contoh:

Outlet OFF pukul 09:00 selama 60 menit.

Dashboard menampilkan:

**Akan buka kembali pada 10:00 WIB**

Setelah durasi selesai:

### **Jika sedang dalam jam operasional**

Bot otomatis membuka outlet.

### **Jika sedang di luar jam operasional**

Bot menunggu jadwal operasional berikutnya.

---

# **21\. OFF SEPANJANG HARI**

"Sepanjang hari" **tidak berarti sampai pukul 23:59 atau 00:00.**

Artinya:

> Outlet tetap OFF untuk seluruh sisa periode operasional pada hari tersebut.

Outlet otomatis ON kembali pada **jam operasional pertama di hari berikutnya**.

### **Contoh**

Jam operasional:

* 06:00–10:00  
* 12:00–18:00

Merchant melakukan:

**OFF Sepanjang Hari pukul 09:00**

Maka:

* 09:00–10:00 → OFF  
* 10:00–12:00 → di luar jam operasional  
* 12:00–18:00 → tetap OFF  
* hari berikutnya pada jadwal buka pertama → ON otomatis

---

# **22\. OFF SAMPAI WAKTU TERTENTU**

Merchant/Admin dapat menentukan waktu buka kembali secara spesifik.

Waktu dapat melintasi hari.

Contoh:

**Akan buka kembali pada**  
**29 Agustus 2026, 13:00 WIB**

### **Batas maksimum**

Waktu tertentu maksimal:

**6 bulan kalender sejak waktu OFF ditentukan.**

Bukan 180 hari.

---

# **23\. OFF HINGGA DINYALAKAN KEMBALI**

Mode ini tidak memiliki auto-resume berdasarkan timer.

Outlet tetap dalam desired state OFF sampai:

* merchant menyalakan ON; atau  
* Admin menyalakan ON.

Manual ON membatalkan status OFF sebelumnya.

---

# **24\. OFF OVERRIDE TERHADAP JAM OPERASIONAL**

OFF duration harus tetap dihormati walaupun terjadi pergantian slot jam operasional.

### **Contoh**

Jam operasional:

* 06:00–10:00  
* 12:00–18:00

Merchant memilih:

**OFF 09:00 sampai 13:00**

Maka:

* 09:00–10:00 → OFF  
* 10:00–12:00 → outlet memang di luar jam operasional  
* 12:00 → outlet **tidak boleh otomatis buka**  
* 12:00–13:00 → tetap OFF  
* 13:00 → Bot membuka outlet

Dengan demikian:

**Active OFF override mengalahkan auto-ON pada awal jam operasional.**

---

# **25\. BEHAVIOR DI LUAR JAM OPERASIONAL**

Requirement ini **menggantikan behavior pada brief lama**.

Ketika outlet berada di luar jam operasional:

### **Toggle**

Toggle otomatis tampil:

**OFF**

dan menjadi:

**disabled / tidak dapat dinyalakan.**

Merchant maupun Admin tidak dapat memaksa outlet ON dari toggle ketika sedang di luar jam operasional.

### **Status**

Dashboard menampilkan:

> **Di luar jam operasional**

Jam operasional berikutnya tetap ditampilkan.

---

# **26\. AUTO ON SAAT JAM OPERASIONAL DIMULAI**

Ketika memasuki jadwal operasional berikutnya:

### **Jika tidak ada OFF override aktif**

Toggle otomatis berubah menjadi ON dan Bot menjaga outlet tetap terbuka.

### **Jika masih terdapat OFF override**

Outlet tetap OFF sampai periode OFF selesai.

---

# **27\. SOURCE OF TRUTH OPERASIONAL**

Agar tidak ambigu:

## **Selama jam operasional**

Desired state Dashboard menjadi acuan kontrol.

## **Di luar jam operasional**

Jadwal/status ShopeeFood menjadi boundary utama dan toggle tidak dapat digunakan untuk memaksa ON.

Dengan demikian Bot tidak pernah digunakan untuk membuka outlet di luar jadwal operasional Shopee.

---

# **28\. STATUS YANG DITAMPILKAN KE USER**

Dashboard harus mempunyai indikator sederhana yang terpisah dari toggle:

### **Sedang Buka**

atau

### **Sedang Tutup**

Tidak perlu menampilkan warning khusus jika secara temporer status Shopee belum sama dengan toggle karena Bot akan melakukan sinkronisasi secara otomatis.

---

# **29\. INFORMASI AUTO RESUME**

Saat outlet OFF dengan batas waktu, dashboard harus menampilkan secara eksplisit:

> **Akan buka kembali pada ...**

Jika masih dalam hari yang sama, dapat berupa:

**Akan buka kembali pada 13:00 WIB**

Jika lintas hari:

**Akan buka kembali pada 29 Agustus 2026, 13:00 WIB**

Jika OFF manual:

**OFF hingga dinyalakan kembali**

---

# **30\. INFORMASI OTOMATISASI**

Landing page merchant perlu memberikan penjelasan sederhana bahwa Bot akan otomatis menyalakan kembali outlet sesuai rule.

Contoh copy:

> Bot akan otomatis membuka kembali outlet sesuai waktu yang dipilih dan jam operasional ShopeeFood.

---

# **31\. CTA MENUJU SHOPEEFOOD**

Setiap outlet pada landing page Agency harus mempunyai CTA.

Contoh label:

**Lihat Outlet di ShopeeFood**

Tujuan CTA:

Merchant dapat melihat restorannya sebagaimana dilihat oleh customer.

Jika perangkat mendukung, merchant diarahkan langsung menuju aplikasi ShopeeFood/customer perspective outlet tersebut.

Mekanisme deep link merupakan keputusan teknis tim Tech.

---

# **32\. DASHBOARD ADMIN — NAVIGASI**

Minimum navigation:

1. **Agency**  
2. **Virtual Brand**  
3. **Logs**  
4. **Settings**

Dashboard saat ini dapat digunakan sebagai baseline visual tetapi struktur informasi perlu mengikuti requirement terbaru dalam dokumen ini.

---

# **33\. DASHBOARD ADMIN — AGENCY SUMMARY**

Bagian atas halaman Agency harus mempunyai widget summary.

Minimum:

### **Total Outlet**

Jumlah Store ID Agency yang sedang dikelola.

### **Buka**

Jumlah outlet dengan status buka.

### **Tutup**

Jumlah outlet dengan status tutup.

Summary harus berubah mengikuti data/filter yang relevan jika UX memerlukan contextual summary.

---

# **34\. FILTER — AGENCY**

Minimum filter yang diperlukan:

* Search nama pemilik;  
* Search nama outlet;  
* Search Store ID;  
* Status Aktif/Nonaktif;  
* status Buka/Tutup;

Filter dapat dikombinasikan.

---

# **35\. AGENCY LIST**

Minimum informasi per outlet pada Admin Dashboard:

* Nama Pemilik;  
* Merchant Name;  
* Nama Panjang Outlet;  
* Store ID;  
* Status master Aktif/Nonaktif;  
* Paket;  
* periode layanan;  
* jam operasional;  
* status Buka/Tutup;  
* toggle;  
* informasi auto-resume jika ada;  
* aktivitas terakhir.

---

# **36\. BULK CONTROL — AGENCY**

Admin harus dapat:

1. memilih beberapa outlet;  
2. menjalankan satu action toggle terhadap semua outlet terpilih.

Agency selection dilakukan di level:

**Store ID / outlet individual.**

Contoh:

Admin memilih 12 outlet dan melakukan OFF.

Sebelum proses:

* pilih durasi OFF;  
* tampilkan confirmation modal.

Contoh:

> Anda akan mematikan 12 outlet. Lanjutkan?

Setelah dikonfirmasi, proses dijalankan.

---

# **37\. DASHBOARD VIRTUAL BRAND — UNIT KONTROL**

Pada VB:

**Selection dilakukan pada level grup, bukan Store ID individual.**

Contoh grup:

**Katsunami**

Jika Katsunami mempunyai 7 Store ID dalam row tersebut, satu toggle Katsunami diterapkan kepada seluruh Store ID valid dalam grup tersebut.

Store ID kosong diabaikan.

---

# **38\. DASHBOARD VB — SUMMARY**

VB perlu mempunyai summary dalam **dua level**.

## **A. Group Summary**

* Total Grup VB  
* Grup ON  
* Grup OFF

## **B. Store ID Summary**

* Total Store ID  
* Store ID Buka  
* Store ID Tutup

Dengan demikian Admin dapat mengetahui sekaligus:

* berapa grup yang dikelola;  
* berapa akun ShopeeFood/store sebenarnya yang berada di balik seluruh grup tersebut.

---

# **39\. FILTER — VB**

Minimum filter:

* Search Nama Outlet Asli / Grup;  
* Status Aktif/Nonaktif;  
* status ON/OFF;  
* portal;  
* Store ID.

---

# **40\. INFORMASI PER GRUP VB**

Minimum informasi yang perlu tersedia:

### **Header grup**

* Nama Outlet Asli;  
* status Aktif/Nonaktif;  
* toggle grup;  
* status grup;  
* waktu auto-resume jika ada;  
* aktivitas terakhir.

### **Detail anggota**

Untuk setiap Store ID valid:

* portal;  
* Store ID;  
* jam operasional;  
* status outlet.

Satu grup dapat mempunyai jam operasional yang berbeda untuk masing-masing Store ID.

Karena itu jam operasional VB harus tetap tersedia **per Store ID**.

---

# **41\. BULK ACTION — VB**

Admin dapat:

1. memilih beberapa **grup VB**;  
2. memilih ON atau OFF;  
3. jika OFF, menentukan durasi;  
4. mengkonfirmasi action;  
5. sistem mengeksekusi action ke seluruh Store ID valid pada grup-grup tersebut.

Admin tidak melakukan bulk selection langsung terhadap Store ID individual dari halaman utama VB.

---

# **42\. CONFIRMATION BULK ACTION**

Sebelum bulk action dijalankan wajib muncul confirmation.

Contoh:

> **Matikan 5 Grup VB?**  
> Action akan diterapkan kepada seluruh Store ID aktif dalam grup yang dipilih.

CTA:

**Batal**  
**Konfirmasi**

---

# **43\. PROCESS INDICATOR**

Setelah bulk action dikonfirmasi, Dashboard harus menunjukkan bahwa proses sedang berlangsung.

User tidak boleh merasa action selesai sebelum seluruh target selesai diproses.

Contoh status:

> **Sedang memproses...**

atau progress indicator/loading yang relevan.

---

# **44\. RESULT BULK ACTION**

Setelah selesai, tampilkan summary.

Contoh:

> **Proses selesai**  
> 18 berhasil  
> 2 gagal

Jika terdapat failure, masing-masing target yang gagal dapat mempunyai keterangan pendek.

Contoh:

**Gagal — outlet tidak dapat diproses**

Tidak perlu membuat banyak kategori failure pada UI.

Semua cukup berada dalam satu status:

**Gagal**

dengan short reason bila diperlukan.

---

# **45\. PARTIAL FAILURE**

Kegagalan pada satu Store ID tidak boleh menyebabkan Store ID lain berhenti diproses.

Contoh:

Satu grup mempunyai 8 Store ID.

Jika:

* 7 berhasil;  
* 1 gagal;

maka hasil akhir:

**7 berhasil, 1 gagal**

bukan seluruh grup dianggap gagal total tanpa pemrosesan lainnya.

---

# **46\. MERCHANT LANDING PAGE — INFORMASI OUTLET**

Setiap outlet Agency minimal menampilkan:

* Merchant Name;  
* Nama Panjang Outlet;  
* Store ID;  
* status Buka/Tutup;  
* jam operasional;  
* toggle ON/OFF;  
* informasi "Akan buka kembali pada..." jika ada;  
* activity terakhir;  
* CTA ke ShopeeFood.

---

# **47\. MERCHANT LANDING PAGE — MULTI OUTLET**

Jika satu pemilik mempunyai banyak outlet, seluruh outlet ditampilkan di landing page pemilik tersebut.

Merchant tidak perlu login berkali-kali untuk masing-masing Store ID.

Satu password membuka seluruh outlet milik pemilik yang terkait dengan unique link tersebut.

---

# **48\. ACTIVITY LOG**

Sistem harus mencatat seluruh aktivitas yang relevan terhadap buka/tutup outlet.

Aktor dibedakan menjadi:

### **Merchant**

Action dilakukan dari landing page merchant.

### **Admin**

Action dilakukan dari Admin FoodMaster.

### **Bot**

Action dilakukan otomatis oleh sistem.

---

# **49\. EVENT YANG MASUK LOG**

Minimum user-facing activity:

* toggle ON oleh Merchant;  
* toggle OFF oleh Merchant;  
* toggle ON oleh Admin;  
* toggle OFF oleh Admin;  
* Bot membuka outlet;  
* Bot menutup outlet;  
* Bot melakukan auto-resume.

Log tidak perlu menjelaskan panjang lebar *mengapa* suatu action dilakukan.

Aktor harus jelas.

---

# **50\. FORMAT LOG MERCHANT**

Merchant hanya perlu melihat:

**20 activity terakhir.**

Tidak perlu:

* pagination;  
* load more;  
* infinite scroll untuk history lama.

Minimum informasi:

* tanggal;  
* jam;  
* zona waktu;  
* outlet;  
* action;  
* aktor: Admin / Merchant / Bot.

Contoh:

**26 Aug 2026 · 13:00 WIB**  
Outlet Surabaya  
**Dibuka — Bot**

---

# **51\. ADMIN LOGS**

Admin Dashboard tetap mempunyai halaman Logs terpusat.

Admin dapat menelusuri activity seluruh Agency dan VB.

Minimum filter:

* periode waktu;  
* Agency / VB;  
* merchant/grup;  
* Store ID;  
* aktor;  
* action;  
* berhasil/gagal.

Admin logs dapat mempunyai detail lebih lengkap dibanding merchant-facing logs.

---

# **52\. TIDAK ADA LIMIT TOGGLE**

Merchant maupun Admin dapat melakukan perubahan toggle tanpa batas jumlah perubahan harian.

Tidak ada:

* daily quota;  
* cooldown bisnis;  
* maksimum toggle per hari.

Pembatasan teknis jika diperlukan untuk keamanan merupakan concern tim Tech dan tidak boleh mengubah pengalaman bisnis tanpa approval Product Owner.

---

# **53\. SETTINGS ADMIN**

Settings digunakan untuk administrasi akun FoodMaster.

Minimum:

* melihat Admin;  
* mengubah username Admin;  
* mengubah password Admin;  
* menambah Admin.

Settings bukan tempat untuk mengubah master data outlet.

Master data tetap berada di Google Sheet.

---

# **54\. SECURITY REQUIREMENT**

### **Merchant Agency**

* unique landing page per pemilik;  
* password-only access;  
* password dibuat Admin;  
* merchant tidak dapat mengganti password;  
* merchant hanya melihat data miliknya.

### **VB**

* internal FoodMaster;  
* tidak membutuhkan merchant password.

### **Credential Shopee**

Credential operasional tidak boleh diperlihatkan kepada merchant.

---

# **55\. UI STATE YANG WAJIB ADA**

Sistem minimal mempunyai state berikut:

### **Normal ON**

**Sedang Buka**

### **Normal OFF**

**Sedang Tutup**

### **Temporary OFF**

**Akan buka kembali pada \[tanggal/jam/timezone\]**

### **Manual OFF**

**OFF hingga dinyalakan kembali**

### **Outside Operating Hours**

**Di luar jam operasional**

Toggle disabled.

### **Subscription Expired**

**Layanan berakhir**

Toggle disabled.

### **Processing**

**Sedang memproses...**

### **Success**

**Berhasil**

### **Failure**

**Gagal**

dengan short reason jika diperlukan.

---

# **56\. CONTOH FLOW 1 — AGENCY NORMAL**

Jam operasional:

08:00–22:00.

Pukul 09:00:

* subscription aktif;  
* Status row Aktif;  
* toggle ON.

Bot memastikan outlet terbuka.

Jika ShopeeFood menutup outlet sementara:

Bot membuka kembali outlet agar sesuai desired state ON.

---

# **57\. CONTOH FLOW 2 — OFF 60 MENIT**

Pukul 12:00 merchant menekan OFF.

Sistem menampilkan pilihan duration.

Merchant memilih:

**60 menit**

Merchant confirm.

Outlet ditutup.

Dashboard menampilkan:

**Akan buka kembali pada 13:00 WIB**

Pukul 13:00:

Bot otomatis membuka outlet jika masih berada dalam jam operasional.

---

# **58\. CONTOH FLOW 3 — BREAK JAM OPERASIONAL**

Jam operasional:

06:00–10:00  
12:00–18:00

Tidak terdapat OFF override.

Pukul 10:00:

* memasuki outside operating hours;  
* toggle berubah OFF;  
* toggle disabled;  
* dashboard menampilkan "Di luar jam operasional".

Pukul 12:00:

* jam operasional dimulai;  
* toggle otomatis ON;  
* Bot memastikan outlet terbuka.

---

# **59\. CONTOH FLOW 4 — OFF MELEWATI BREAK**

Jam operasional:

06:00–10:00  
12:00–18:00

Pukul 09:00:

Merchant memilih OFF sampai 13:00.

Pukul 10:00:

Outlet masuk outside operating hours.

Pukul 12:00:

Jam operasional kembali dimulai tetapi OFF override masih berlaku.

Outlet tetap tertutup.

Pukul 13:00:

OFF selesai.

Bot membuka outlet.

---

# **60\. CONTOH FLOW 5 — SUBSCRIPTION HABIS**

Tanggal layanan berakhir.

Bot berhenti mengendalikan outlet.

Outlet tidak otomatis ditutup.

Landing page menampilkan:

**Layanan berakhir**

Toggle disabled.

Admin memperpanjang tanggal di Google Sheet dan melakukan Fetch.

Jika tanggal kembali valid:

layanan otomatis aktif kembali.

---

# **61\. CONTOH FLOW 6 — VB**

Grup:

**Katsunami**

Store ID:

* SuperFood A  
* WonderFood A  
* Lokarasa A  
* Do Eat A  
* Do Eat B  
* Do Eat C

Admin menekan OFF pada grup Katsunami.

Admin memilih duration.

Setelah confirmation:

Bot menerapkan OFF kepada seluruh Store ID valid dalam row Katsunami.

Cell kosong dilewati.

---

# **62\. CONTOH FLOW 7 — BULK VB**

Admin memilih:

* Katsunami  
* Lakubudi  
* Minang Agung  
* Depot 88

Admin memilih:

**OFF 60 menit**

Confirmation muncul.

Admin confirm.

Dashboard menampilkan loading/progress.

Setelah selesai:

> 21 Store ID berhasil  
> 2 Store ID gagal

Target gagal mempunyai short reason.

Target lain tetap dianggap berhasil dan tidak perlu diulang.

---

# **63\. UX PRINCIPLE**

Dashboard harus terasa seperti **control panel operasional**, bukan database viewer.

Prioritas tampilan:

1. Apa status outlet sekarang?  
2. Apakah Bot aktif?  
3. Apakah outlet sedang ON atau OFF?  
4. Jika OFF, kapan akan buka kembali?  
5. Apa jam operasionalnya?  
6. Siapa yang terakhir mengubah status?  
7. Apakah user perlu melakukan tindakan?

Data teknis sekunder tidak boleh mengganggu tugas utama tersebut.

---

# **64\. HAL YANG TIDAK PERLU DITAMPILKAN KE MERCHANT**

Merchant tidak perlu melihat:

* credential ShopeePartner;  
* detail teknis Bot;  
* polling interval;  
* scheduler;  
* retry mechanism;  
* technical exception;  
* server status internal;  
* struktur database;  
* data merchant lain.

Merchant hanya membutuhkan kontrol dan informasi operasional.

---

# **65\. KEPUTUSAN YANG MENJADI DOMAIN TIM TECH**

Brief ini menetapkan **business requirement dan user requirement**, bukan arsitektur implementasi.

Tim Tech menentukan:

* interval pengecekan Bot;  
* scheduler;  
* queue;  
* worker;  
* retry strategy;  
* timeout;  
* database structure;  
* caching;  
* session management;  
* encryption implementation;  
* Shopee deep-link implementation;  
* infrastructure;  
* framework;  
* hosting;  
* logging backend.

Keputusan teknis tersebut diperbolehkan selama tidak mengubah behavior bisnis dalam brief ini.

---

# **66\. ACCEPTANCE CRITERIA — MASTER DATA**

Implementasi dianggap sesuai jika:

* Google Sheet tetap menjadi master data;  
* master data tidak diedit dari Dashboard;  
* Fetch dari Sheet tersedia di Dashboard;  
* Agency \= 1 row / 1 Store ID;  
* VB \= 1 row / 1 grup;  
* cell Store ID VB kosong dilewati;  
* Status Aktif/Nonaktif dihormati;  
* tanggal layanan hanya berlaku untuk Agency;  
* VB tidak mempunyai subscription date logic.

---

# **67\. ACCEPTANCE CRITERIA — AGENCY**

* satu owner dapat mempunyai banyak outlet;  
* satu owner mempunyai satu unique landing page;  
* login hanya menggunakan password;  
* password dibuat Admin;  
* password tidak wajib unik;  
* merchant tidak dapat mengganti password;  
* merchant hanya melihat outlet miliknya;  
* merchant dan Admin mempunyai authority toggle yang setara;  
* merchant dapat memilih duration OFF;  
* subscription expired menghentikan Bot tanpa mengubah status outlet;  
* extension subscription otomatis mengaktifkan layanan kembali.

---

# **68\. ACCEPTANCE CRITERIA — BOT LOGIC**

* Bot tidak membuka outlet di luar jam operasional;  
* toggle di luar jam operasional tampil OFF;  
* toggle di luar jam operasional disabled;  
* toggle otomatis ON ketika jam operasional dimulai;  
* active OFF override tetap dihormati;  
* OFF 30 menit berjalan;  
* OFF 60 menit berjalan;  
* OFF sepanjang hari berjalan;  
* OFF sampai waktu tertentu berjalan;  
* waktu tertentu dibatasi maksimal 6 bulan kalender;  
* OFF manual berjalan;  
* auto-resume bekerja;  
* timezone mengikuti outlet.

---

# **69\. ACCEPTANCE CRITERIA — DASHBOARD**

### **Agency**

* summary Total/Buka/Tutup tersedia;  
* filter tersedia;  
* bulk selection tersedia;  
* bulk toggle tersedia.

### **VB**

* summary grup tersedia;  
* summary Store ID tersedia;  
* selection dilakukan per grup;  
* satu toggle grup diterapkan ke seluruh Store ID valid;  
* bulk action mempunyai confirmation;  
* proses mempunyai loading/progress;  
* result menampilkan berhasil/gagal;  
* failure dapat mempunyai short reason.

---

# **70\. ACCEPTANCE CRITERIA — MERCHANT UX**

Merchant dapat dengan cepat mengetahui:

* outlet apa yang dimilikinya;  
* Store ID;  
* jam operasional;  
* sedang buka atau tutup;  
* toggle ON/OFF;  
* jika OFF, kapan akan buka kembali;  
* 20 activity terakhir;  
* siapa yang melakukan action;  
* CTA menuju outlet ShopeeFood.

---

# **71\. ACCEPTANCE CRITERIA — LOGS**

Semua action buka/tutup yang dilakukan oleh:

* Merchant;  
* Admin;  
* Bot;

dapat ditelusuri.

Log menyimpan waktu beserta timezone.

Merchant menampilkan maksimum 20 activity terakhir tanpa Load More.

Admin memiliki Logs terpusat.

---

# **72\. FINAL PRODUCT DEFINITION**

Produk akhir bukan sekadar "Bot yang membuka ShopeeFood".

Produk terdiri atas tiga layer:

### **1\. Master Data Layer**

Google Sheet FoodMaster.

### **2\. Control & Visibility Layer**

Admin Dashboard \+ Merchant Landing Page.

### **3\. Automation Layer**

Bot ShopeeFood yang menjaga outlet mengikuti desired state selama diizinkan oleh jam operasional dan business rule.

Tujuan akhirnya adalah membuat proses buka/tutup outlet ShopeeFood menjadi:

**mudah dikendalikan, otomatis, dapat dipantau, dan dapat ditelusuri**, baik untuk merchant Agency maupun operasional Virtual Brand FoodMaster.

---

## **RULE PALING PENTING UNTUK TIM TECH**

> **Agency:** satu Store ID \= satu toggle.  
> **VB:** satu grup pada Kolom A \= satu toggle untuk seluruh Store ID valid pada row tersebut.

> **Dalam jam operasional:** Dashboard menentukan desired state.

> **Di luar jam operasional:** toggle OFF dan disabled sampai jam operasional berikutnya.

> **OFF timer yang masih aktif mengalahkan auto-ON jam operasional.**

> **Subscription hanya berlaku pada Agency.**

> **Status Aktif/Nonaktif adalah master gate terpisah dari subscription dan toggle.**

> **Admin dan merchant Agency mempunyai authority toggle yang setara.**

> **Setiap action Admin, Merchant, dan Bot harus dapat ditelusuri melalui log.**

