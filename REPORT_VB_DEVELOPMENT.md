# Development Report — Tab `VB` / Virtual Brand

Status dokumen: bahan diskusi, belum merupakan spesifikasi final dan belum mengubah source code.

## 1. Ringkasan pemahaman

`VB` adalah mode operasional yang berbeda dari bot-oc outlet biasa:

- kontrol ditampilkan satu baris per brand/merk;
- kunci brand berasal dari kolom `Nama Outlet Asli`;
- satu brand memiliki banyak outlet/store ID;
- outlet dapat tersebar pada beberapa merchant/portal Shopee;
- satu toggle brand berlaku ke seluruh outlet brand tersebut;
- default toggle brand adalah `ON`;
- ketika brand diubah ke `OFF`, seluruh outlet yang tergabung pada brand tersebut menjadi target penutupan;
- ketika brand diubah ke `ON`, seluruh outlet yang tergabung menjadi target pembukaan, dengan tetap memperhatikan aturan operasional yang nantinya disepakati.

Makna pentingnya: pada mode VB, `Nama Outlet Asli` bukan nama outlet yang dikontrol satu per satu, melainkan identitas virtual brand/group. Store ID tetap menjadi target teknis aksi di Shopee.

## 2. Hasil pembacaan spreadsheet

Sumber data yang dibaca:

<https://docs.google.com/spreadsheets/d/e/2PACX-1vSTEPFClRQogVXYHNo3PRN4m91wHoKHSpS6Dg5Ofj08JFZdoCS9apvvh3C2OTVpqpebFk6xhaQs6ljY/pub?gid=2099001096&single=true&output=csv>

Struktur aktual CSV:

| Posisi | Header | Makna untuk VB |
|---|---|---|
| 1 | `Nama Outlet Asli` | Nama brand/group, kunci utama VB |
| 2 | `SuperFood` | Merchant/portal; isi berupa Store ID |
| 3 | `WonderFood` | Merchant/portal; isi berupa Store ID |
| 4 | `Lokarasa` | Merchant/portal; isi berupa Store ID |
| 5–7 | `Gurame Bakar, Do Eat` | Merchant/portal yang sama, tetapi memiliki beberapa kolom outlet |

Temuan data:

- 27 brand/group pada baris data;
- 6 kolom merchant, tetapi hanya 4 nama merchant unik;
- 107 Store ID terisi dan semuanya unik pada snapshot ini;
- satu brand dapat mempunyai Store ID pada 1 sampai 4 merchant unik;
- header `Gurame Bakar, Do Eat` berulang tiga kali. Posisi kolom harus dipertahankan saat parsing karena setiap kolom berisi outlet berbeda;
- spreadsheet ini tidak menyediakan kolom toggle VB. Toggle harus dikelola oleh aplikasi/database;
- spreadsheet ini tidak menyediakan status aktual Shopee. Status aktual tetap harus dibaca dari Shopee saat cycle.

Contoh pola grouping:

```text
Brand: Katsunami
  SuperFood              -> 21758652
  WonderFood             -> 21897202
  Lokarasa               -> 21901665
  Gurame Bakar, Do Eat   -> 22426766, 22386259, 22300083
```

## 3. Landasan sistem bot-oc yang sudah ada

### Sumber data runtime

Arsitektur yang terdokumentasi menetapkan PostgreSQL sebagai source of truth runtime, sedangkan Google Spreadsheet digunakan untuk import/master data. Implementasi worker juga mengambil outlet dari database dan bukan membaca spreadsheet setiap kali aksi dijalankan.

### Hierarki saat ini

```text
Mitra (merchants)
  └── Portal/merchant Shopee (portals)
        └── Outlet/store (outlets, store_id)
              └── outlet_states
```

Hierarki tersebut cocok untuk bot-oc biasa karena `vercel_status` berada di `outlet_states`, sehingga satu toggle mewakili satu outlet.

### Cycle saat ini

Secara ringkas, daemon bot-oc:

1. memastikan hanya satu daemon aktif;
2. melakukan warmup/login session akun Shopee;
3. memeriksa status jaringan dan status pause daemon;
4. mengambil outlet dari database;
5. mengelompokkan outlet berdasarkan `(username, nama_portal)`;
6. memastikan session/browser berada pada merchant yang benar;
7. membaca status aktual setiap `store_id`;
8. mengevaluasi decision engine;
9. menjalankan open/close bila target berbeda dari status aktual;
10. melakukan verifikasi pasca-aksi dan menyimpan log;
11. mengulang sesuai interval, default 60 detik.

### Prioritas decision engine saat ini

Bot-oc biasa menggunakan urutan:

1. suspension;
2. subscription;
3. jam operasional;
4. toggle `vercel_status`;
5. status aktual Shopee untuk menentukan apakah aksi diperlukan.

Untuk VB, posisi toggle harus dipindahkan secara konseptual dari level outlet ke level brand. Jangan membuat satu toggle VB lalu menyalinnya sebagai toggle independen ke outlet, karena hal itu berisiko membuat state brand dan state outlet tidak konsisten.

## 4. Perbedaan desain VB terhadap bot-oc biasa

| Aspek | Bot-oc biasa | VB |
|---|---|---|
| Baris UI | Satu outlet | Satu brand |
| Kunci kontrol | Store/outlet | `Nama Outlet Asli`/brand |
| Target aksi | Satu Store ID | Semua Store ID brand |
| Relasi merchant | Outlet berada pada satu portal | Brand dapat lintas portal |
| Toggle | Per outlet | Satu per brand |
| Default awal | Saat ini schema outlet `OFF` | Harus `ON` untuk brand VB |
| Proses cycle | Evaluasi outlet | Resolusi brand lalu eksekusi ke outlet anggota |
| Risiko utama | Salah target satu outlet | Partial failure pada sebagian outlet lintas merchant |

## 5. Dampak terhadap database

### Rekomendasi utama: tambah model brand VB terpisah

Modifikasi minimal yang paling aman adalah menambah entitas khusus VB, tanpa menjadikan `merchants` atau `outlets` sebagai pengganti brand:

```text
vb_brands
  ├── vb_brand_states       (satu toggle untuk satu brand)
  └── vb_brand_outlets      (relasi brand -> outlet/store)
                                └── outlets -> portals -> shopee_accounts
```

Bentuk konseptual tabel:

### `vb_brands`

- `id` — primary key;
- `name` — nilai normalisasi dari `Nama Outlet Asli`;
- `display_name` — nama yang ditampilkan di tab;
- `control_status` — `ON`/`OFF`, default `ON`;
- `is_active` — mengaktifkan/nonaktifkan konfigurasi brand;
- `source` dan metadata import bila diperlukan;
- timestamp perubahan.

Constraint yang disarankan: nama brand unik setelah aturan normalisasi disepakati. Jangan memakai nama tampilan mentah tanpa aturan whitespace/case yang konsisten.

### `vb_brand_outlets`

- `vb_brand_id`;
- `outlet_id` atau `store_id`;
- `source_column` — opsional tetapi berguna untuk melacak merchant column asal;
- timestamp import.

Gunakan unique constraint pada pasangan `(vb_brand_id, outlet_id)`. `store_id` tetap identitas teknis outlet dan tidak boleh diganti dengan nama brand.

### `vb_brand_states` atau state langsung pada `vb_brands`

Untuk kebutuhan awal, `control_status` dapat langsung berada di `vb_brands`. Jika perlu menyimpan status actual agregat atau histori perubahan, gunakan tabel state terpisah dan audit log. Status actual sebaiknya tetap per outlet karena Shopee mengembalikan status per Store ID.

### Log

Log perlu membedakan:

- perubahan toggle brand oleh admin (`VB_TOGGLE_CHANGED`);
- cycle brand (`VB_SYNC_CYCLE`);
- aksi teknis per Store ID (`ACTION_OPEN`/`ACTION_CLOSE`);
- hasil partial success/failed per outlet;
- `vb_brand_id`, nama brand, merchant/portal, dan Store ID.

Log level brand saja tidak cukup untuk troubleshooting karena satu cycle dapat berhasil pada sebagian merchant dan gagal pada sebagian lainnya.

## 6. Import mapping yang diusulkan

Spreadsheet VB berbentuk matrix, sehingga proses import perlu diubah dari parser baris-outlet menjadi parser matrix:

```text
for setiap baris:
    brand = kolom pertama
    untuk setiap kolom merchant mulai kolom kedua:
        jika cell berisi Store ID:
            buat/temukan outlet berdasarkan Store ID
            buat/temukan brand berdasarkan brand
            buat relasi brand -> outlet
```

Header merchant yang berulang tidak boleh digabung secara naif sebelum cell diproses. Posisi kolom 5, 6, dan 7 semuanya harus menghasilkan relasi outlet terpisah di bawah merchant `Gurame Bakar, Do Eat`.

Import harus idempotent: menjalankan import ulang tidak boleh menggandakan brand, outlet, atau relasi. Brand yang hilang dari snapshot baru juga perlu kebijakan eksplisit: nonaktifkan, hapus relasi, atau pertahankan sebagai data historis. Rekomendasi awal adalah tidak menghapus otomatis.

## 7. Rancangan perilaku tab `VB`

Kolom UI minimum per baris:

| Kolom | Keterangan |
|---|---|
| Brand | `Nama Outlet Asli` |
| Jumlah outlet | Total Store ID yang terhubung |
| Merchant | Daftar merchant unik, atau ringkasan jumlah merchant |
| Toggle VB | ON/OFF, default ON |
| Status eksekusi | Sinkron, proses, partial failure, atau error |
| Last sync | Waktu cycle terakhir |
| Detail | Membuka daftar merchant dan Store ID anggota |

Saat toggle diubah:

1. simpan perubahan brand-level ke database;
2. catat audit log;
3. cycle berikutnya membaca state brand tersebut;
4. cycle mencari seluruh outlet anggota;
5. aksi dijalankan per Store ID, grouped by account dan portal;
6. hasil setiap outlet disimpan, termasuk jika hanya sebagian berhasil.

Default `ON` hanya berarti desired/control state baru untuk VB. Pada initial import, sistem tetap perlu menentukan apakah langsung menjalankan pembukaan semua 107 outlet atau menunggu cycle pertama setelah validasi. Rekomendasi aman untuk diskusi: import state `ON`, lalu cycle normal melakukan rekonsiliasi dan log eksplisit.

## 8. Rancangan cycle VB

```text
Load VB brands + brand control state
        |
Resolve all related outlets/store IDs
        |
Group by Shopee account + merchant portal
        |
Switch/verify merchant context
        |
Read actual status per Store ID
        |
Resolve brand target ON/OFF
        |
Open/close each outlet that differs
        |
Verify each result + write per-outlet logs
        |
Write brand aggregate result
```

Hal yang harus dijaga:

- satu brand tidak boleh diproses sebagai satu `store_id` fiktif;
- satu kegagalan merchant tidak boleh menghentikan outlet brand yang berada di merchant lain;
- browser/session tetap dapat dipakai ulang seperti bot-oc sekarang;
- merchant switch dilakukan per portal, sementara keputusan target berasal dari brand;
- retry harus idempotent dan tidak menganggap aksi yang gagal sebagai sukses;
- aggregate status brand perlu menunjukkan `SYNCED`, `PARTIAL_FAILURE`, atau `FAILED`, bukan hanya ON/OFF.

## 9. Apakah perlu modifikasi database?

Ya, hampir pasti perlu. Schema saat ini menyimpan control state pada `outlet_states.vercel_status`, sedangkan kebutuhan VB memerlukan satu control state untuk kumpulan outlet lintas portal.

Alternatif yang perlu dipilih:

1. **Tabel VB terpisah (rekomendasi):** isolasi domain dan tidak merusak perilaku bot-oc lama.
2. Menambah `brand_id` dan tipe mode ke tabel existing: lebih sedikit tabel, tetapi coupling tinggi dan rawan mencampur semantics outlet biasa dengan VB.
3. Hanya memakai `merchants.name` sebagai brand: tidak cocok karena pada sistem existing merchant berarti pemilik/mitra dan portal berarti merchant Shopee.

Rekomendasi saya adalah opsi pertama dengan migration baru, setelah aturan bisnis final disetujui.

## 10. Keputusan yang masih perlu dibahas

Sebelum implementasi, perlu dikunci:

- apakah `Nama Outlet Asli` selalu brand, atau ada baris yang sebenarnya nama outlet individual;
- apakah satu Store ID boleh terhubung ke lebih dari satu brand;
- apakah ON VB melewati subscription, suspension, dan jam operasional bot-oc, atau VB hanya mengikuti toggle brand;
- apakah OFF harus langsung menutup semua outlet atau hanya memengaruhi cycle berikutnya;
- apakah perubahan toggle hanya boleh admin;
- perilaku saat import menemukan brand baru, brand hilang, atau Store ID berpindah brand;
- apakah initial default ON boleh men-trigger aksi nyata saat import pertama;
- apakah satu brand boleh memiliki beberapa akun Shopee yang berbeda;
- bentuk notifikasi ketika hanya sebagian outlet berhasil;
- apakah tab VB berada pada dashboard admin yang sama dan memakai endpoint terpisah.

## 11. Tahapan development setelah spesifikasi disepakati

1. Finalisasi aturan prioritas VB dan definisi ON/OFF.
2. Finalisasi model `vb_brands` dan relasi `vb_brand_outlets`.
3. Buat migration database baru dan uji terhadap data existing.
4. Buat import matrix spreadsheet yang idempotent.
5. Tambah API tab VB dan audit/logging.
6. Tambah UI toggle per brand dengan detail outlet/merchant.
7. Integrasikan evaluator VB ke cycle worker tanpa mengubah decision flow bot-oc biasa.
8. Uji dry-run: grouping, merchant switch, target resolution, partial failure, retry, dan default ON.
9. Uji aksi nyata terbatas pada satu brand sebelum rollout seluruh dataset.

## Kesimpulan

Kebutuhan VB dipahami sebagai kontrol pada level brand, bukan variasi tampilan dari kontrol outlet. Spreadsheet menyediakan mapping brand ke Store ID lintas merchant, tetapi bukan state operasional. Karena itu, data matrix perlu diimport ke relasi brand–outlet, toggle perlu disimpan di level brand dengan default `ON`, dan cycle perlu tetap mengeksekusi aksi teknis satu per Store ID setelah grouping berdasarkan merchant/account.

Belum ada skrip atau perubahan kode pada tahap ini; dokumen ini menjadi dasar diskusi langkah berikutnya.
