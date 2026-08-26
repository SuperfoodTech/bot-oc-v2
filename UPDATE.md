# Update

## Latest update: v1.10.1

### Server safety fix v1.10.1

- `bot-vb` dikembalikan ke `HEADLESS=true` untuk kompatibilitas server Docker
  tanpa display/X server.
- Catatan eksperimen `HEADLESS=false` dihapus dari riwayat update aktif.
- Detail lengkap tersedia di [update/1.10.1.md](update/1.10.1.md).

## Update v1.10.0

- Runtime VB tidak lagi dipengaruhi `penangguhan` atau masa aktif layanan.
- Setelah gate jadwal dan status khusus Shopee, target action hanya ditentukan
  oleh toggle Virtual Brand admin.
- Worker VB dan bot-OC tetap tidak berubah.
- Detail lengkap tersedia di [update/1.10.0.md](update/1.10.0.md).

### Build/runtime fix v1.9.2

- Memperbaiki import daemon VB agar memakai `sync_all_stores` dari worker yang
  sudah disamakan dengan bot-OC.
- Detail lengkap tersedia di [update/1.9.2.md](update/1.9.2.md).

### Build fix v1.9.1

- Build context Docker sekarang mengecualikan seluruh `src/data/**` karena
  seluruh data runtime dipasang melalui volume; ini mencegah cache Chrome
  dengan permission lokal menghambat build `bot-vb`.
- Detail lengkap tersedia di [update/1.9.1.md](update/1.9.1.md).

- `main-vb/src/worker.py` sekarang identik byte-for-byte dengan worker bot-OC.
- Core `decision`, `sheets`, `import_sheet`, `browser`, dan `store_status` VB
  disamakan dengan bot-OC.
- Adapter database VB membaca target toggle dari `vb_brands.applied_status`,
  hanya outlet dari brand aktif, menyimpan schedule/status Shopee, dan memberi
  label log `VB` agar tidak tercampur dengan log bot-OC.
- Tidak ada perubahan pada `main-bot/src/worker.py`.
- Detail lengkap tersedia di [update/1.9.0.md](update/1.9.0.md).

## Update v1.8.0

- `main-vb/src/core/browser.py` sekarang identik 100% dengan
  `src/core/browser.py`.
- Perbedaan VB hanya berasal dari environment variable credential, session,
  dan Chrome profile.
- Detail lengkap tersedia di [update/1.8.0.md](update/1.8.0.md).

## Update v1.7.5

- Menyamakan normalisasi status live `bot-vb` dengan `bot-oc`: hanya status
  dengan `pause_start_time` aktif yang dianggap `PAUSE`; status non-OPEN lain
  menjadi `CLOSED`.
- Detail lengkap tersedia di [update/1.7.5.md](update/1.7.5.md).

## Update v1.7.4

- Menyamakan `bot-vb` dengan `bot-oc` untuk pause timed: `pause_until` brand
  diteruskan sebagai `pause_end_time` Unix milliseconds ke XHR Shopee.
- Detail lengkap tersedia di [update/1.7.4.md](update/1.7.4.md).

## Update v1.7.3

- Memperbaiki kalkulasi opsi `rest_of_day` agar selalu menggunakan timezone
  WIB dan tidak gagal saat dikurangi dengan waktu timezone-aware.
- Detail lengkap tersedia di [update/1.7.3.md](update/1.7.3.md).

## Update v1.7.2

- Memperbaiki filter status VB agar brand lama yang sudah tidak ada di Sheet
  juga dinonaktifkan.
- Database VB sekarang mengikuti Sheet VB sebagai source of truth; brand yang
  hilang atau berstatus nonaktif tidak masuk scope dashboard maupun bot.
- Dashboard sekarang menampilkan jumlah brand aktif dan brand yang
  dinonaktifkan pada hasil import.
- Detail lengkap tersedia di [update/1.7.2.md](update/1.7.2.md).

## Update v1.7.1

- Memperbaiki sumber Google Sheet VB menggunakan tab `gid=401458905` yang
  valid dan mengembalikan CSV.
- Detail lengkap tersedia di [update/1.7.1.md](update/1.7.1.md).

## Update v1.7.0

- Import VB sekarang memakai kolom `Status` sebagai filter scope seperti Bot
  O/C: hanya status aktif yang diproses oleh dashboard dan bot.
- Brand nonaktif dikeluarkan dari scope, dan dapat aktif kembali saat status
  Sheet berubah menjadi aktif.
- Detail lengkap tersedia di [update/1.7.0.md](update/1.7.0.md).

## Update v1.6.3

- Konfigurasi `HEADLESS` dipusatkan ke satu variabel di file `.env`.
- Service `bot-oc` dan `bot-vb` sekarang membaca nilai `HEADLESS` yang sama
  melalui Docker Compose.
- Detail lengkap tersedia di [update/1.6.3.md](update/1.6.3.md).

## Update v1.6.2

- Konfigurasi browser `bot-vb` dikembalikan ke mode headless (`HEADLESS=true`)
  agar stabil di server dan Docker tanpa display.
- Detail lengkap tersedia di [update/1.6.2.md](update/1.6.2.md).

## Update v1.6.0

- Toggle Virtual Brand sekarang memiliki modal pilihan durasi pause dan
  penyimpanan `pause_until` pada level brand.
- Pause otomatis mengajukan status `ON` setelah waktunya berakhir.
- Detail lengkap tersedia di [update/1.6.0.md](update/1.6.0.md).

## Update v1.5.1

- Memperbaiki status `PAUSE` Shopee agar tidak salah terdeteksi sebagai
  `CLOSED` atau jadwal khusus pada `bot-oc`.
- Detail lengkap tersedia di [update/1.5.1.md](update/1.5.1.md).

## Update v1.5.0

- `bot-oc` melewati outlet secara diam-diam di luar jadwal operasional tanpa
  menjalankan aksi atau mengirim report skip.
- Toggle dashboard mitra tampil OFF dan disabled di luar jadwal, dengan toast
  merah `Di luar jadwal operasional` saat dicoba.
- Detail lengkap tersedia di [update/1.5.0.md](update/1.5.0.md).

- `bot-vb` tidak lagi melaporkan outlet yang statusnya sudah sesuai sebagai
  skip pada log operasional default.
- Report hanya dibuat untuk kegagalan aksi, switch merchant, driver,
  exception, atau validasi pasca-aksi.
- Detail lengkap tersedia di [update/1.4.5.md](update/1.4.5.md).

## Update v1.4.4

- Memastikan foreground seluruh toast Virtual Brand menggunakan warna putih.
- Detail lengkap tersedia di [update/1.4.4.md](update/1.4.4.md).

## Update v1.4.3

- Mengubah toggle Virtual Brand menjadi merah solid saat aktif.
- Menyamakan desain toast admin dengan toast dashboard mitra, termasuk posisi, warna solid, ikon, dan animasi keluar.
- Detail lengkap tersedia di [update/1.4.3.md](update/1.4.3.md).

## Update v1.4.2

- Menghapus background tombol `X` bottom sheet dan menggunakan simbol merah.
- Meningkatkan visibilitas font mobile admin dengan warna lebih gelap, ukuran lebih besar, dan bobot lebih tebal.
- Detail lengkap tersedia di [update/1.4.2.md](update/1.4.2.md).

## Update v1.4.1

- Memperbaiki alignment simbol `X` agar tepat berada di tengah tombol close bottom sheet.
- Detail lengkap tersedia di [update/1.4.1.md](update/1.4.1.md).

## Update v1.4.0

- Menambahkan tombol `Lihat jadwal` pada detail outlet admin desktop.
- Menambahkan tombol `Lihat jadwal` di samping `Hapus akun` pada card admin mobile.
- Jadwal mobile tampil sebagai bottom sheet dengan handle tarik dan tombol `X`.
- Detail lengkap tersedia di [update/1.4.0.md](update/1.4.0.md).

## Update v1.3.0

- Menambahkan tombol `Lihat jadwal` pada detail outlet dashboard admin.
- Jadwal reguler Shopee ditampilkan per outlet dalam panel informasi.
- Detail lengkap tersedia di [update/1.3.0.md](update/1.3.0.md).

## Update v1.2.3

- Menggunakan font Nunito khusus pada halaman login admin.
- Detail lengkap tersedia di [update/1.2.3.md](update/1.2.3.md).

## Update v1.2.2

- Memperbarui cache-busting asset CSS agar style jadwal reguler Shopee terbaru termuat setelah deployment.
- Detail lengkap tersedia di [update/1.2.2.md](update/1.2.2.md).

## Update v1.2.1

- Menghapus tulisan `Read-only` dari tampilan jadwal reguler Shopee.
- Detail lengkap tersedia di [update/1.2.1.md](update/1.2.1.md).

## Update v1.2.0

- Mengambil dan menyimpan jadwal reguler Shopee melalui XHR yang sama dengan fetch status.
- Menambahkan tampilan jadwal read-only per outlet dengan arrow merah.
- Local owner `Yolo` memakai data dummy dari `DOCS/reguler-hours-response.json` tanpa menjalankan bot.
- Detail lengkap tersedia di [update/1.2.0.md](update/1.2.0.md).

## Update v1.1.19

- Membatasi pilihan tanggal pause custom maksimal 6 bulan kalender dari tanggal sekarang sesuai aturan Shopee.
- Contoh: 24 Agustus 2026 dibatasi sampai 24 Februari 2027.
- Detail lengkap tersedia di [update/1.1.19.md](update/1.1.19.md).

## Update v1.1.18

- Menambahkan efek disabled pada field `Mulai` ketika memilih `Durasi lain`.
- Detail lengkap tersedia di [update/1.1.18.md](update/1.1.18.md).

## Update v1.1.17

- Memusatkan modal pause dan modal konfirmasi open secara vertikal di layar.
- Detail lengkap tersedia di [update/1.1.17.md](update/1.1.17.md).

## Update v1.1.16

- Memindahkan ID/store ID ke pojok kanan atas card outlet.
- Menambahkan hari dan tanggal lengkap pada preview target pause yang dipilih.
- Detail lengkap tersedia di [update/1.1.16.md](update/1.1.16.md).

## Update v1.1.15

- Mengubah label `Aktif` pada kartu akun mitra menjadi merah solid dengan foreground putih.
- Detail lengkap tersedia di [update/1.1.15.md](update/1.1.15.md).

## Update v1.1.14

- Menambahkan tulisan `Butuh bantuan?` di sebelah ikon customer service.
- Teks dan ikon tetap menjadi satu link menuju WhatsApp admin.
- Detail lengkap tersedia di [update/1.1.14.md](update/1.1.14.md).

## Update v1.1.13

- Mengganti visual ikon WhatsApp menjadi ikon customer service/headset.
- Tujuan klik tetap menuju WhatsApp admin melalui `wa.me`.
- Detail lengkap tersedia di [update/1.1.13.md](update/1.1.13.md).

## Update v1.1.12

- Mengganti tombol teks Bantuan menjadi ikon customer service.
- Ikon mengarahkan mitra ke WhatsApp admin melalui `wa.me`.
- Detail lengkap tersedia di [update/1.1.12.md](update/1.1.12.md).

## Update v1.1.11

- Menempatkan pill waktu buka sejajar dengan pill remaining time di bawah judul `Buka otomatis`.
- Detail lengkap tersedia di [update/1.1.11.md](update/1.1.11.md).

## Update v1.1.10

- Mengubah background pill informasi `Ditutup oleh bot sampai ...` menjadi merah solid dengan foreground putih.
- Detail lengkap tersedia di [update/1.1.10.md](update/1.1.10.md).

## Update v1.1.9

- Merapikan label log bot dengan menghapus redundansi teks `(Bot)` karena sudah diwakili pill `Bot`.
- Menyesuaikan jarak antara baris action dan label waktu agar lebih proporsional.
- Detail lengkap tersedia di [update/1.1.9.md](update/1.1.9.md).

## Update v1.1.8

- Memperbaiki pill `Bot` agar berukuran sesuai isi dan tidak melebar memenuhi baris.
- Menampilkan waktu action bot dengan pill kuning dan informasi penutupan sampai waktu tertentu dengan pill hijau.
- Menghapus teks redundan `Dibuka oleh bot` pada action open.
- Detail lengkap tersedia di [update/1.1.8.md](update/1.1.8.md).

## Update v1.1.7

- Menampilkan action bot `open` dan `close` pada log mitra dengan pill biru.
- Menambahkan dummy log action bot khusus owner `Yolo` di local tanpa menyalakan bot.
- Log close menampilkan waktu aksi dan waktu target buka; log open menampilkan waktu pembukaan.
- Detail lengkap tersedia di [update/1.1.7.md](update/1.1.7.md).

## Update v1.1.6

- Menambahkan animasi keluar toast berupa fade-out sambil bergerak ke atas sebelum toast disembunyikan.
- Detail lengkap tersedia di [update/1.1.6.md](update/1.1.6.md).

## Update v1.1.5

- Menambahkan toast sukses di atas-tengah dengan warna hijau solid dan animasi ceklis untuk aksi pause/open.
- Menambahkan modal konfirmasi saat membuka outlet dengan tombol `Batal` dan `Lanjut`.
- Menukar urutan tombol modal pause menjadi `Batal` di kiri dan `Simpan` di kanan.
- Detail lengkap tersedia di [update/1.1.5.md](update/1.1.5.md).

## Update v1.1.4

- Membatasi fallback status dummy hanya pada environment local (`localhost`, `127.0.0.1`, atau `::1`).
- Server menampilkan `Shopee: Status belum tersedia` ketika status XHR belum tersedia dan tidak menerima nilai dummy.
- Detail lengkap tersedia di [update/1.1.4.md](update/1.1.4.md).

## Update v1.1.3

- Menampilkan status Shopee terakhir yang diterima dari fetch XHR pada label di samping nama outlet.
- Menormalkan status `ON`/`OPEN` menjadi `Shopee: Buka` dan `PAUSE`/`CLOSED` menjadi `Shopee: Tutup sementara`.
- Memastikan label waktu buka hanya menampilkan `HH:MM WIB`.
- Detail lengkap tersedia di [update/1.1.3.md](update/1.1.3.md).

## Update v1.1.2

- Memperbaiki parsing offset timestamp PostgreSQL seperti `+00`.
- Menampilkan waktu buka hanya `HH:MM WIB` dan remaining time pada pill hijau.
- Detail lengkap tersedia di [update/1.1.2.md](update/1.1.2.md).

## Update v1.1.1

- Menyinkronkan toggle internal menjadi ON setelah pause terjadwal Shopee selesai.
- Dashboard memuat ulang status setelah countdown berakhir tanpa menyalakan bot.
- Detail lengkap tersedia di [update/1.1.1.md](update/1.1.1.md).

## Update v1.1.0

- Menambahkan pill kuning berisi waktu buka exact dan pill hijau berisi
  remaining time pada card outlet mitra.
- Kedua pill menggunakan foreground putih dan rounded 50%.
- Detail lengkap tersedia di [update/1.1.0.md](update/1.1.0.md).

## Update v1.0.0

- Memperbaiki penerusan durasi pause dashboard ke payload Shopee melalui
  `pause_end_time` Unix timestamp milidetik.
- Menambahkan countdown sisa pause menuju outlet kembali ON.
- Menyeragamkan timezone tampilan dan log ke WIB/GMT+7 tanpa fractional seconds
  atau microseconds.
- Memperbesar dan mempertebal teks status serta log agar lebih mudah dibaca.
- Detail lengkap tersedia di [update/1.0.0.md](update/1.0.0.md).

## Latest deployment handoff

- Docker service definition for `bot-vb` was added to `docker-compose.yml`.
- The service uses the shared `foodmaster-bot-runtime:dev` image and the existing
  dependency layer; no second dependency installation is required.
- Server runtime is explicitly `HEADLESS=true`.
- The change was committed and pushed to `origin/main` as `0c3d5e9`.
- Docker build/start has not been executed from this development workspace;
  deployment must be performed by the server AI agent using the instructions
  below.

## Virtual Brand Bot

- Added the `main-vb` patrol service with brand-level controls and merchant switching.
- Added VB database migrations for brand mappings, removal of `ownership_type`, compact bot observability, and outlet-level error tracing.
- Added the Virtual Brand admin tab with brand cards, merchant/outlet details, and brand-level ON/PAUSED control.
- Unified the Logs tab for Bot O/C and Virtual Brand with compact summaries, recent changes, and traceable Store ID errors.
- Updated the regular spreadsheet importer for the current 11-column layout after removal of the ownership column.
- Configured VB to use `main-vb/src/data/session.json`, `main-vb/src/data/credentials.json`, and the `shopee_profile` Chrome subprofile.
- VB browser uses `HEADLESS=true` in the server Docker service; local debugging may override this explicitly.

## Server deployment: Bot VB Docker service

Bot VB now has its own service, `fm-bot-vb`, while reusing the same image and
dependency environment as `fm-bot`. There is no separate VB dependency
installation and no public VB port.

The service is configured server-side with `HEADLESS=true` and uses:

- `/app/vb-data/chrome_profile` for the VB Chrome profile;
- `/app/vb-data/session.json` for the VB session;
- `/app/vb-data/credentials.json` for the VB credential file;
- Chrome subprofile `shopee_profile`;
- the existing `fm-postgres` database network.

The host `src/data` directory is mounted at `/app/vb-data`; this avoids relying
on the local symlinks under `main-vb/src/data` inside the container.

### AI agent deployment instructions

1. Ensure the host files exist and are not committed:
   `src/data/chrome_profile`, `src/data/session.json`, and
   `src/data/credentials allvbadmin.json`.
2. The compose service maps the host credential file to
   `/app/vb-data/credentials.json` as read-only; verify the source file exists.
3. Build and start only the VB service with:

   ```bash
   docker compose build bot-vb
   docker compose up -d bot-vb
   ```

4. Verify startup with:

   ```bash
   docker compose ps bot-vb
   docker compose logs --tail=100 -f bot-vb
   ```

5. Confirm the logs contain `headless=True`, the `/app/vb-data/chrome_profile`
   path, and `shopee_profile`. Confirm the first patrol reports a brand,
   merchant, Store ID, action, and result.

6. Stop or restart only this service when needed:

   ```bash
   docker compose stop bot-vb
   docker compose restart bot-vb
   ```

Do not add a second dependency install, do not expose a new port, and do not
mount the VB profile into `fm-bot`. The VB service performs real Shopee actions
according to the persisted brand states.

## Validation

- Python compilation passed for `src` and `main-vb/src`.
- Admin dashboard JavaScript syntax validation passed.
- PostgreSQL migrations through `006_log_overview_and_errors` applied successfully.
- Regular spreadsheet fetch and VB import were validated against the configured sources.
