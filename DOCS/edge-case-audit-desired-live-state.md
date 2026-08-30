# Edge Case Audit: Desired State, Live State, Multi-Schedule, and Patrol Loop

Dokumen ini merangkum edge case penting yang muncul dari kontrak `desired state` vs `live state`, perilaku Shopee pada multi-schedule, dan cara bot berputar di codebase saat ini.

Tujuan dokumen ini:
- Menjelaskan edge case dengan bahasa operasional, bukan hanya istilah teknis.
- Menunjukkan apa yang dulu salah.
- Menjelaskan apa yang sekarang sudah berubah secara praktis.
- Menandai mana yang benar-benar selesai, mana yang baru teratasi sebagian, dan mana yang masih jadi known gap.

Dokumen ini merefleksikan kondisi codebase saat ini. Ini belum berarti sistem sudah menjadi `merchant-aware scheduler` penuh. Saat ini kita baru sampai pada tahap:
- traversal per `merchant group` saat eksekusi worker, dan
- hardening pada `decision engine`, `runtime state`, `worker wake hint`, dan validasi context outlet Shopee.

## 1. Mental Model

Sebelum masuk ke edge case, ini model berpikir yang dipakai sekarang:

### Desired State
Desired state adalah keadaan yang diinginkan sistem internal kita.

Sumber utamanya:
- `vercel_status`
- `pause_until`
- suspension admin
- status langganan

Nilai akhirnya:
- `OPEN`
- `PAUSE`
- `MANUAL_OFF`

### Live State
Live state adalah keadaan nyata yang sedang terjadi di Shopee saat bot membaca status outlet.

Nilai utamanya:
- `OPEN`
- `PAUSE`
- `CLOSED`
- `UNKNOWN`

### Prinsip yang dipakai sekarang
1. Jika outlet sedang `suspended`, bot tidak boleh membuka outlet.
2. Jika langganan tidak aktif, bot tidak boleh membuka outlet.
3. Jika ada `pause_until` aktif, bot harus menjaga outlet tetap tutup sampai waktunya habis.
4. Jika di luar jadwal reguler Shopee, status `CLOSED` dianggap normal dan tidak dilawan bot.
5. Jika masih dalam jadwal reguler Shopee dan desired state adalah `OPEN`, maka `PAUSE` atau `CLOSED` dari Shopee dianggap mismatch yang harus dijaga bot.

Itu berarti titik bedanya sekarang adalah:
- `CLOSED di luar jadwal` = normal.
- `CLOSED di dalam jadwal saat toggle ON` = bukan normal, harus dijaga dan dibuka kembali.

## 2. Ringkasan Status Edge Case

| ID | Edge case | Contoh praktik | Status sekarang | Dampak praktis sekarang | Sisa risiko |
|---|---|---|---|---|---|
| EC-01 | Toggle ON, Shopee `CLOSED/PAUSE`, masih dalam jadwal | Shopee menutup random outlet jam 12:10 saat jadwal 09:00-21:00 | Teratasi | Bot menganggap ini `PENDING_OPEN` dan akan mencoba membuka lagi | Tetap bergantung pada frekuensi patrol |
| EC-02 | Pause aktif melewati break multi-schedule | Jadwal 12:00-13:40 dan 14:00-15:00, pause sampai 14:30 | Teratasi | Bot menjaga outlet tetap tutup saat sesi kedua mulai | Masih ada gap jika boundary lewat saat cycle belum selesai |
| EC-03 | Boundary jadwal lewat di tengah cycle | Cycle mulai 13:45, selesai 14:01, sesi kedua mulai 14:00 | Teratasi sebagian kuat | Bot bisa bangun lagi hampir langsung setelah cycle selesai | Belum preempt current cycle di tengah jalan |
| EC-04 | DB menulis status palsu setelah action | Action open terkirim, verify live gagal, DB dulu langsung ditulis `ON` | Teratasi | DB hanya diupdate kalau live state benar-benar terbaca | UI bisa tetap pending sampai recheck berikutnya |
| EC-05 | Dua sync overlap dalam satu process | Admin trigger sync saat daemon masih sync | Teratasi | Cycle kedua akan di-skip | Hanya aman dalam satu process |
| EC-06 | Salah context outlet setelah switch merchant / antar outlet | Browser masih di outlet A, tapi worker kira sudah outlet B | Teratasi sebagian | Fetch/action sekarang mensyaratkan `storeId` target tervalidasi | Endpoint Shopee live status masih bergantung pada page context |
| EC-07 | Session browser mati di tengah batch | Driver mati setelah beberapa outlet | Teratasi sebagian | Worker cek kesiapan session per outlet dan mencoba recovery | Jika recovery terus gagal, outlet menunggu cycle berikutnya |
| EC-08 | Query DB tidak membawa akun Shopee yang benar | Semua outlet terbaca seolah memakai username default | Teratasi sebagian | Grouping worker dan recovery session jauh lebih benar | Jika relasi DB outlet-account belum rapi, fallback default masih dipakai |
| EC-09 | Pause expired belum tercermin di admin endpoint | `pause_until` sudah lewat tapi admin dashboard masih melihat OFF | Teratasi | Endpoint admin ikut sync expired pause sebelum response | Browser tetap butuh refresh/fetch ulang |
| EC-10 | Jadwal gagal di-fetch | API reguler hours gagal atau empty | Aman tapi degrade | Bot tetap pakai jadwal valid terakhir jika ada | Jika belum pernah punya jadwal valid, bot tidak bisa jaga penuh |
| EC-11 | Dicoret: overnight single-interval | Jadwal `20:00-04:00` tidak bisa dibuat di Shopee | Tidak relevan untuk domain | Tidak perlu fix khusus | Lintas tengah malam harus dimodelkan sebagai dua jadwal dan boundary biasa |
| EC-12 | Shopee menutup random tepat setelah outlet selesai dipatrol | Bot cek jam 12:00, Shopee menutup jam 12:02 | Belum teratasi penuh | Akan tertangkap di patrol berikutnya | Belum ada watcher atau priority queue real-time |
| EC-13 | Scheduler belum merchant-aware penuh | Merchant besar dan kecil masih ikut rotasi global | Belum teratasi | Switching di dalam merchant group sudah lebih efisien | Urutan merchant belum diprioritaskan secara dinamis |

## 3. Detail Per Edge Case

### EC-01. Toggle ON, live `CLOSED/PAUSE`, masih dalam jadwal

### Contoh praktik
- Hari: Senin, 31 Agustus 2026
- Jadwal reguler Shopee: `09:00-21:00`
- Jam sekarang: `12:10 WIB`
- Toggle dashboard: `ON`
- Live state Shopee: `CLOSED`

### Masalah sebelum perubahan
Sebelumnya ada asumsi keras:
- jika Shopee `CLOSED` saat masih dalam jam reguler,
- maka itu dianggap `jadwal khusus Shopee`,
- lalu bot memilih `NO_CHANGE`.

Dampaknya:
- outlet bisa tetap tutup padahal merchant membayar layanan penjagaan outlet,
- toggle `ON` tidak benar-benar jadi sumber kebenaran saat operasional aktif,
- dashboard memberi kesan outlet memang "wajar tutup", padahal sebenarnya mismatch.

### Perilaku sekarang
Sekarang logikanya berubah:
- jika masih dalam jadwal reguler,
- desired state `OPEN`,
- live state `PAUSE` atau `CLOSED`,
- maka outlet dianggap `PENDING_OPEN`.

Dampak praktis:
- bot akan mencoba `ACTION_OPEN`,
- dashboard user dan admin akan menampilkan label:
  - `Sedang Tutup • Menunggu bot membuka`
- ini lebih jujur terhadap kondisi sebenarnya: outlet masih tutup, tapi sistem kita memang sedang mengoreksi.

### Nilai bisnis
Ini adalah perubahan paling penting untuk use case "penjagaan outlet" karena random close dari Shopee sekarang diperlakukan sebagai mismatch yang harus dijaga, bukan sebagai final truth.

### Referensi implementasi
- `src/core/decision.py`
- `src/backend/db.py::derive_outlet_runtime_state`
- `src/backend/templates/user_dashboard.html`
- `src/backend/templates/admin_dashboard.html`

### EC-02. Pause aktif yang melewati break multi-schedule

### Contoh praktik
Merchant punya dua jadwal pada Sabtu, 29 Agustus 2026:
- `12:00-13:40`
- `14:00-15:00`

Kondisi:
- Jam `13:30 WIB`, user meminta tutup sementara sampai `14:30 WIB`

### Kenapa ini tricky
Pada `13:40`, sesi pertama selesai dan Shopee memang menutup outlet.
Masalah terjadi saat `14:00`:
- Shopee bisa membuka lagi karena sesi kedua mulai,
- padahal pause user masih aktif sampai `14:30`.

### Masalah sebelum perubahan
Tanpa logika multi-schedule yang benar, sistem bisa salah berpikir:
- "outlet sudah tertutup kok, selesai"

Padahal secara bisnis:
- pause user belum selesai,
- jadi ketika sesi kedua mulai, bot harus tetap menjaga outlet agar tutup sampai `14:30`.

### Perilaku sekarang
Sekarang pause aktif diperlakukan melintasi break antar sesi reguler.

Artinya:
1. Jika masih break antar sesi, bot tidak perlu paksa apa-apa.
2. Tapi bot menghitung sesi reguler berikutnya sebelum `pause_until`.
3. Saat sesi kedua mulai, bot akan recheck cepat.
4. Jika outlet terbuka lagi oleh Shopee, bot akan menutup ulang karena pause masih aktif.

### Dampak praktis
Pause tidak lagi "hilang" hanya karena outlet kebetulan sudah tertutup saat break antar jadwal.

### Referensi implementasi
- `src/core/decision.py::get_next_schedule_start`
- `src/core/decision.py::get_pause_recheck_delay_seconds`

### EC-03. Boundary jadwal lewat di tengah cycle

### Contoh praktik
Masih memakai contoh multi-schedule yang sama:
- break pada `13:40-14:00`
- sesi kedua mulai `14:00`
- bot mulai cycle besar pada `13:45`
- karena banyak merchant, cycle baru selesai `14:01`

### Masalah sebelum perubahan
Sebelumnya wake hint dihitung memakai "waktu saat selesai cycle" tanpa mempertimbangkan bahwa:
- ketika cycle dimulai, bot sebenarnya sudah tahu ada boundary penting di `14:00`,
- tetapi boundary itu keburu lewat selama cycle berjalan.

Akibatnya:
- bot bisa tidur lagi mengikuti interval default,
- misalnya 15 menit atau bahkan lebih lama,
- sehingga outlet bisa salah state lebih lama dari yang seharusnya.

### Perilaku sekarang
Sekarang worker memisahkan dua waktu:
- `cycle_started_at`
- `cycle_finished_at`

Lalu wake hint dihitung seperti ini:
1. Boundary penting dicari dari perspektif `cycle_started_at`
2. Delay aktual dihitung terhadap `cycle_finished_at`
3. Jika deadline ternyata sudah lewat saat cycle selesai, worker mengembalikan delay `1 detik`

### Dampak praktis
Kalau sesi kedua mulai saat bot masih muter, bot tidak akan tidur panjang lagi. Ia akan langsung muter lagi hampir seketika.

### Kenapa ini masih "teratasi sebagian"
Karena bot belum bisa menyela cycle yang sedang berjalan.

Artinya:
- jika boundary lewat pada menit ke-2 dari cycle,
- dan cycle selesai pada menit ke-6,
- outlet tetap berpotensi salah state selama 4 menit itu.

Jadi ini sudah jauh lebih aman, tapi belum sekelas scheduler preemptive atau priority queue real-time.

### Referensi implementasi
- `main-bot/src/worker.py`
- `src/core/decision.py`

### EC-04. DB menulis status palsu setelah action

### Contoh praktik
- Bot mengirim `ACTION_OPEN`
- Request action sukses terkirim
- Tapi request verifikasi live status gagal timeout

### Masalah sebelum perubahan
Sebelumnya worker bisa langsung menulis status ekspektasi ke DB:
- target `OPEN` -> DB diisi `ON`
- target `CLOSE` -> DB diisi `PAUSE`

Padahal live state sebenarnya belum berhasil diverifikasi.

Risikonya:
- dashboard terlihat sinkron padahal belum,
- cycle berikutnya bisa membuat keputusan berdasarkan data yang terlalu optimistis,
- troubleshooting jadi membingungkan.

### Perilaku sekarang
Sekarang DB hanya diupdate kalau post-action verification benar-benar berhasil membaca live state.

Jika verify gagal:
- DB tidak dipaksa menulis state ekspektasi,
- worker menjadwalkan fast recheck tambahan.

### Dampak praktis
Sistem sekarang lebih jujur.
Kalau belum tahu hasil akhirnya, status akan tetap tampak pending atau last-known, bukan pura-pura sudah sinkron.

### Tradeoff
UI bisa terlihat "lebih lambat menjadi hijau", tapi itu justru lebih benar daripada false positive.

### EC-05. Dua sync overlap dalam satu process

### Contoh praktik
- Daemon sedang sync
- Admin menekan tombol trigger sync manual di waktu yang sama

### Masalah sebelum perubahan
Kalau dua sync berjalan bersamaan:
- outlet yang sama bisa dibaca dua kali,
- action open/pause bisa terkirim ganda,
- log audit jadi membingungkan.

### Perilaku sekarang
Ada `SYNC_LOCK` level process.

Jika satu cycle masih berjalan:
- cycle kedua tidak ikut masuk,
- tetapi langsung return `sync_skipped`.

### Dampak praktis
Perilaku worker dalam satu daemon sekarang jauh lebih stabil dan lebih mudah diprediksi.

### Kenapa belum penuh
Lock ini hanya in-memory.
Kalau ada:
- dua process,
- dua container,
- atau dua instance deployment,

maka overlap antar instance masih mungkin terjadi.

### EC-06. Salah context outlet setelah switch merchant atau antar outlet

### Contoh praktik
- Merchant A punya outlet `Store 101` dan `Store 102`
- Worker selesai memproses `Store 101`
- Browser masih berada di halaman `Store 101`
- Worker lanjut ke `Store 102`

### Masalah sebelum perubahan
Sebelumnya validasi `Business Hours` terlalu longgar:
- cukup halaman terlihat seperti menu business hours,
- tetapi belum memastikan `storeId` target benar-benar aktif.

Akibatnya:
- fetch live status bisa membaca outlet yang salah,
- action open/pause berisiko dilakukan dalam context outlet yang salah.

### Perilaku sekarang
Sekarang halaman dianggap valid hanya jika:
- URL cocok ke halaman `business-hours`, dan
- `storeId` di URL cocok dengan target outlet

Selain itu:
- fetch live status,
- fetch regular hours,
- open action,
- pause action

tidak akan lanjut jika validasi halaman gagal.

### Dampak praktis
Risiko cross-outlet contamination jauh turun, terutama pada merchant yang punya banyak outlet.

### Kenapa masih "teratasi sebagian"
Karena endpoint live status Shopee yang dipakai sekarang masih:
- `GET /api/seller/store`
- tanpa parameter `store_id`

Jadi sumber kebenaran live status masih mengandalkan page context browser yang benar.
Sekarang context itu sudah dijaga lebih ketat, tapi belum 100% bebas dari risiko jika Shopee mengubah perilaku context internalnya.

### EC-07. Session browser mati di tengah batch

### Contoh praktik
- Browser login valid saat masuk merchant
- Setelah 15 outlet, session WebDriver mati

### Masalah sebelum perubahan
Sebelumnya pengecekan session lebih banyak dilakukan saat awal merchant group.

Risikonya:
- outlet-outlet berikutnya bisa tetap dicoba memakai session mati,
- banyak fetch/action gagal beruntun,
- delay pemulihan lebih panjang.

### Perilaku sekarang
Sekarang worker:
- mengecek kesiapan session sebelum patrol tiap outlet,
- mencoba recovery jika driver mati,
- mengulang validasi setelah recovery,
- dan juga mengecek lagi menjelang post-action verification.

### Dampak praktis
Worker jadi lebih tahan terhadap kematian session di tengah batch besar.

### Kenapa masih "teratasi sebagian"
Kalau recovery gagal berulang:
- worker tetap tidak bisa memaksa outlet pulih saat itu juga,
- outlet akan tertunda sampai cycle berikutnya atau sampai session recovery sukses.

### EC-08. Query DB tidak membawa akun Shopee yang benar

### Contoh praktik
- Dua merchant memakai akun Shopee yang berbeda
- Query runtime justru mengembalikan username konstan default
- Password dan phone terbaca kosong

### Masalah sebelum perubahan
Ini masalah yang kelihatannya kecil, tapi dampaknya besar:
- grouping worker per akun bisa salah,
- recovery session bisa memakai credential yang tidak relevan,
- future merchant-aware scheduling akan rusak karena fondasi data akun tidak benar.

### Perilaku sekarang
Runtime query sekarang membawa:
- `sa.username`
- `sa.phone`
- `sa.password_plain`

lalu worker memakainya saat membangun `MerchantOutlet`.

### Dampak praktis
Grouping dan session bootstrap/recovery sekarang lebih dekat ke data akun Shopee yang sebenarnya.

### Kenapa masih "teratasi sebagian"
Kalau relasi `outlet -> shopee_account` di DB belum lengkap atau masih kosong:
- query tetap fallback ke username default bot,
- jadi masalah data hygiene masih bisa bocor ke runtime.

### EC-09. Pause expired belum tercermin di admin endpoint

### Contoh praktik
- User pause outlet sampai `10:00 WIB`
- Pada `10:05 WIB`, admin membuka daftar store atau detail store

### Masalah sebelum perubahan
Beberapa endpoint admin belum memanggil sinkronisasi `expired pause`.

Akibatnya:
- user endpoint bisa melihat state yang lebih baru,
- tetapi admin endpoint bisa masih membawa state lama.

### Perilaku sekarang
Endpoint admin penting sekarang juga memanggil sinkronisasi `expired pause` sebelum membangun response.

### Dampak praktis
Desired state yang tampil di admin sekarang lebih konsisten dengan runtime rule.

### Catatan
Ini tidak otomatis memaksa browser admin yang sudah membuka halaman untuk berubah sendiri. Tetap dibutuhkan fetch ulang, refresh, atau mekanisme realtime yang memicu render ulang.

### EC-10. Jadwal gagal di-fetch

### Contoh praktik
- Worker berhasil masuk merchant
- Fetch `regular-hours` dari Shopee timeout

### Masalah yang ingin dihindari
Kalau sistem terlalu agresif saat jadwal gagal dibaca:
- bot bisa mengambil keputusan berdasarkan asumsi kosong,
- itu berbahaya untuk outlet yang seharusnya sedang dijaga.

### Perilaku sekarang
Strategi saat ini:
1. Jika sudah ada jadwal valid terakhir, worker tetap memakainya.
2. Jika fetch sekarang gagal, worker tidak langsung membuang jadwal yang lama.
3. Jika memang tidak ada jadwal valid sama sekali, outlet masuk fase `SCHEDULE_UNAVAILABLE`.

### Dampak praktis
Ini aman dari sisi konservatif:
- lebih baik pending daripada salah buka/tutup.

### Tradeoff
Untuk outlet baru yang belum pernah berhasil mengambil jadwal sama sekali:
- bot belum punya fondasi cukup untuk berjaga penuh,
- jadi layanan bersifat degrade, bukan full protection.

### EC-11. Dicoret: overnight single-interval tidak berlaku di domain Shopee

Setelah verifikasi domain bisnis:
- Shopee tidak mendukung satu interval jadwal seperti `20:00-04:00`
- rentang yang valid hanya di dalam hari yang sama, `00:00-23:59`

Jadi jika merchant ingin operasional melewati tengah malam, model yang benar adalah:
- `Jumat 20:00-23:59`
- `Sabtu 00:00-04:00`

Artinya:
- kita tidak perlu membuat hardening khusus untuk `overnight single-interval`
- yang perlu dijaga hanyalah boundary antar jadwal seperti biasa
- problem itu lebih cocok diselesaikan oleh scheduler merchant-aware, bukan rule overnight terpisah

Status akhir untuk EC-11:
- dicoret dari daftar bug aktif
- dianggap `not applicable` untuk domain Shopee saat ini

### EC-12. Shopee menutup random tepat setelah outlet selesai dipatrol

### Contoh praktik
- Bot memeriksa outlet pada `12:00 WIB`
- Outlet saat itu `OPEN`
- Pada `12:02 WIB`, Shopee menutup random karena issue keterlambatan order
- Default patrol berikutnya baru terjadi beberapa menit kemudian

### Status sekarang
Belum tertangani penuh.

### Yang sudah membantu
Perubahan baru membuat:
- mismatch lebih cepat dikenali saat outlet diperiksa lagi,
- action mismatch lebih jujur tercatat,
- fast recheck terjadi jika ada action verify yang gagal atau boundary penting.

### Yang belum ada
Belum ada mekanisme:
- watcher per outlet,
- webhook dari Shopee,
- priority queue outlet rawan,
- atau adaptive polling khusus untuk outlet yang baru saja bermasalah.

### Dampak praktis
Layanan penjagaan outlet sekarang lebih benar secara logika, tetapi masih belum real-time.
Masih ada jendela waktu antara:
- random close terjadi,
- dan patrol berikutnya datang.

### EC-13. Scheduler belum merchant-aware penuh

### Contoh praktik
- Merchant A punya 20 outlet
- Merchant B punya 1 outlet
- Merchant C baru saja mengalami mismatch penting

### Kondisi sekarang
Worker memang sudah lebih efisien karena:
- outlet dikelompokkan per `(username, portal)`
- jadi sekali switch merchant, beberapa outlet dalam merchant itu diproses berurutan

Tetapi penjadwalannya masih belum benar-benar merchant-aware.

### Artinya apa
Belum ada logika persistent seperti:
- merchant dengan mismatch aktif didahulukan,
- merchant yang memiliki outlet pause-boundary terdekat didahulukan,
- merchant yang baru gagal verify diangkat prioritasnya,
- `next_check_at` per merchant atau outlet.

### Dampak praktis
Kita sudah lebih hemat waktu switch merchant, tetapi belum punya scheduler prioritas yang paling optimal untuk penjagaan outlet skala besar.

## 4. Apa yang Sudah Paling Bernilai dari Patch Sekarang

Kalau dilihat dari manfaat praktis, patch saat ini paling terasa di tiga hal:

1. Toggle `ON` sekarang benar-benar berarti "harus buka saat masih dalam jadwal"
   - Ini inti layanan penjagaan outlet.

2. Pause aktif sekarang tidak hilang saat ada break antar sesi reguler
   - Ini penting untuk merchant dengan multi-schedule.

3. Worker sekarang lebih jujur terhadap runtime reality
   - Tidak gampang menulis DB seolah sinkron jika live verification belum sukses.

## 5. Prioritas Hardening Berikutnya

Kalau tujuan berikutnya adalah reliability yang lebih dekat ke production-grade, urutan yang paling masuk akal adalah:

1. Tambahkan scheduler merchant-aware dengan `next_check_at` atau priority queue.
2. Tambahkan distributed lock jika bot bisa jalan lebih dari satu process atau container.
3. Tambahkan adaptive recheck untuk outlet yang baru saja terkena random close dari Shopee.

## 6. File Implementasi yang Relevan

Untuk belajar dari codebase, titik paling pentingnya ada di:
- `src/core/decision.py`
- `src/backend/db.py`
- `main-bot/src/worker.py`
- `src/shopee/store_status.py`
- `src/backend/templates/user_dashboard.html`
- `src/backend/templates/admin_dashboard.html`
- `tests/test_multi_schedule_pause_logic.py`
- `tests/test_outlet_state_contract.py`

## 7. Kesimpulan Praktis

Kalau pertanyaannya adalah:
"Apakah sistem sekarang sudah jauh lebih aman untuk desired state/live state dan multi-schedule?"

Jawabannya: ya.

Kalau pertanyaannya adalah:
"Apakah semua edge case sudah selesai?"

Jawabannya: belum.

Yang sudah selesai adalah bug yang paling merusak kontrak bisnis kita:
- toggle `ON` yang tidak benar-benar menjaga outlet tetap buka saat jam operasional,
- pause yang bisa hilang saat multi-schedule break,
- dan DB yang bisa terlalu optimistis setelah action.

Yang masih perlu dibereskan berikutnya adalah gap reliability tingkat lanjut:
- random close sesaat setelah patrol,
- distributed locking,
- dan merchant-aware scheduler penuh.
