# Proposal Perubahan Database VB

Status: proposal untuk persetujuan sebelum migration dan implementasi API.

Status terbaru: keputusan bisnis telah disetujui dan migration `004_virtual_brand.sql` sudah disiapkan. Deployment database tetap memerlukan backup dan validasi environment.

## Konteks terbaru

`main-vb` menggunakan core terpisah dan credential/session/profile VB sendiri. Database tetap harus menjadi source of truth runtime. Spreadsheet hanya menjadi sumber import mapping brand ke Store ID.

Model existing menyimpan `outlet_states.vercel_status` per outlet. Model tersebut tidak dapat dipakai sebagai satu-satunya control state VB karena satu brand dapat mencakup banyak outlet lintas portal.

## Perubahan yang diusulkan

### 1. `vb_brands`

```text
id                 uuid primary key
name               varchar(255) not null
name_normalized    varchar(255) not null unique
control_status     varchar(3) not null default 'ON'  -- ON/OFF
is_active          boolean not null default true
last_sync_at       timestamptz null
created_at         timestamptz not null
updated_at         timestamptz not null
```

`control_status` adalah satu-satunya toggle yang ditampilkan pada baris brand. Default `ON` berlaku saat brand baru dibuat dari import.

### 2. `vb_brand_outlets`

```text
vb_brand_id        uuid not null references vb_brands(id)
outlet_id          uuid not null references outlets(id)
source_column      varchar(255) null
created_at         timestamptz not null
primary key (vb_brand_id, outlet_id)
```

`outlet_id` tetap mengarah ke Store ID existing. `source_column` menyimpan nama kolom merchant asal untuk audit import, termasuk kolom berulang `Gurame Bakar, Do Eat`.

### 3. `vb_sync_runs`

```text
id                 bigserial primary key
started_at         timestamptz not null
finished_at        timestamptz null
status             varchar(20) not null  -- RUNNING/SYNCED/PARTIAL_FAILURE/FAILED
brands_processed   integer not null default 0
outlets_processed  integer not null default 0
error_message      text null
```

Tabel ini menyimpan ringkasan cycle VB. Detail aksi tetap disimpan per outlet.

### 4. Perluasan `automation_logs`

Tambahkan metadata nullable:

```text
mode               varchar(20) not null default 'OUTLET' -- OUTLET/VB
vb_brand_id        uuid null references vb_brands(id)
vb_sync_run_id     bigint null references vb_sync_runs(id)
```

Dengan ini aksi `ACTION_OPEN` atau `ACTION_CLOSE` tetap tercatat per Store ID, tetapi dapat ditelusuri kembali ke brand dan cycle VB.

### 5. `admin_audit_logs`

Tidak wajib membuat tabel audit baru. Tambahkan `vb_brand_id` nullable agar perubahan toggle dapat direkam:

```text
vb_brand_id        uuid null references vb_brands(id)
```

Action yang disarankan: `VB_CONTROL_STATUS_CHANGED`, `VB_IMPORT`, dan `VB_BRAND_DEACTIVATED`.

## Aturan constraint dan import

- `name_normalized` harus menggunakan aturan konsisten untuk trim whitespace dan case;
- satu Store ID tidak boleh terduplikasi pada brand yang sama;
- satu Store ID boleh memiliki satu atau lebih relasi VB hanya jika bisnis memang mengizinkannya; rekomendasi awal: satu brand aktif per Store ID;
- import ulang harus idempotent;
- brand atau relasi yang hilang dari spreadsheet tidak dihapus otomatis;
- header merchant berulang diproses berdasarkan posisi kolom, bukan hanya nama header;
- credential, session, dan Chrome profile tidak disimpan di database.

## Siklus kontrol yang dihasilkan database

```text
vb_brands.control_status
        |
vb_brand_outlets
        |
outlets.store_id + portals.name + shopee_accounts
        |
per-store actual status dan automation_logs
```

Status kontrol brand menentukan target seluruh anggota. Status aktual tetap per Store ID karena satu outlet dapat gagal atau berbeda status walaupun brand targetnya sama.

## Keputusan yang perlu disetujui

1. Apakah model `vb_brands` + `vb_brand_outlets` disetujui sebagai model terpisah dari control outlet biasa?
2. Apakah satu Store ID boleh berada pada lebih dari satu brand VB?
3. Apakah subscription, suspension, dan business hours existing tetap menjadi guard untuk VB, atau toggle VB menjadi aturan langsung?
4. Apakah default `ON` pada import pertama boleh langsung mengeksekusi open ke semua outlet?
5. Apakah perubahan toggle hanya dapat dilakukan admin?
6. Apakah status aggregate brand perlu tampil `PARTIAL_FAILURE` jika sebagian outlet lintas merchant gagal?

## Rekomendasi

Setujui tabel brand dan relasi terlebih dahulu, pertahankan detail status aktual serta log pada level outlet, dan gunakan migration baru berurutan. Jangan mengubah arti `merchants`, `portals`, atau `outlet_states` existing untuk mengakomodasi VB.

## Keputusan yang sudah disetujui

- subscription dan suspension existing tidak menjadi guard VB;
- pause/resume berlaku pada level brand;
- default brand baru `ON` dan initial `ON` boleh langsung menjalankan open;
- patrol berjalan setiap 30 detik;
- kegagalan otomatis dicoba ulang maksimal 2 kali;
- satu Store ID hanya boleh terhubung ke satu brand VB;
- perubahan hanya dapat dilakukan admin;
- perubahan tidak memotong proses brand yang sedang berjalan;
- perubahan disimpan sebagai pending dan diterapkan saat brand mendapat giliran pada putaran patroli berikutnya;
- Chrome profile VB digunakan eksklusif oleh `main-vb`.
