# Knowledge Transfer & Alignment Guide - Notification Architecture (`bot-oc` & `bot-vb`)

Dokumen ini berisi rangkuman arsitektur, spesifikasi notifikasi, dan aturan operasional untuk alignment antar agent/server.

---

## 0. Handover Update - 2026-09-22

### A. Agency Google Sheet Source Sudah Pindah

- Source Agency aktif sekarang menggunakan published CSV:
  - `https://docs.google.com/spreadsheets/d/e/2PACX-1vSsAq8JmDfGI8KY7aSCRpzC2EaQARkK1OvhWrll7g3qlxFMIcwtDpAF-Wxf4aQnGET4eCmncjdEgre5/pub?gid=890126027&single=true&output=csv`
- Header sheet baru yang sudah tervalidasi:
  - `Nama Pemilik`
  - `Nomor HP`
  - `Status Bot`
  - `Paket`
  - `Tanggal Mulai Layanan`
  - `Tanggal Berakhir Layanan`
  - `Akses Username`
  - `Akses Kata Sandi`
  - `Nama Portal`
  - `Store ID`
  - `Nama Listing`
  - `Vercel Kata Sandi`
- Secara teknis parser Agency tidak perlu perubahan schema karena parser mencari kolom berbasis nama header, dan `Status Bot` tetap tertangkap oleh matcher `status`.

File runtime/fallback yang sudah diarahkan ke source baru:

- `.env`
- `src/core/sheets.py`
- `main-vb/src/core/sheets.py`
- `main-vb/src/sheets.py`
- `main-bot/src/sheets.py`
- `bot-wa/src/index.js`

Catatan operasional penting:

- Untuk perubahan `GOOGLE_SHEETS_CSV_URL` di `.env`, `docker restart fm-backend` saja tidak cukup jika env container belum berubah.
- Gunakan recreate container web:
  - `docker compose up -d --force-recreate --no-deps web`
- Setelah recreate, verifikasi env aktif:
  - `docker inspect fm-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | rg '^GOOGLE_SHEETS_CSV_URL='`

### B. Virtual Brand Source Aktif

- Source VB aktif tetap published CSV relasional 4 kolom:
  - `https://docs.google.com/spreadsheets/d/e/2PACX-1vSsAq8JmDfGI8KY7aSCRpzC2EaQARkK1OvhWrll7g3qlxFMIcwtDpAF-Wxf4aQnGET4eCmncjdEgre5/pub?gid=935753758&single=true&output=csv`
- Struktur aktif:
  - `Owner`
  - `Outlet`
  - `Portal`
  - `Store ID`
- Snapshot tervalidasi saat handover:
  - `113` row outlet valid
  - `29` brand
  - `22` owner
  - `4` portal unik
  - `113` Store ID unik

File runtime VB yang aktif:

- `src/backend/vb.py`
- `main-vb/src/backend/vb.py`
- `main-vb/src/importer.py`

### C. Perubahan Backend VB

- Owner VB sekarang tidak lagi dipaksa menjadi `VB`.
- Import VB sudah menyimpan owner asli per brand:
  - `owner_name`
  - `owner_slug`
- Endpoint public brand sekarang mendukung owner dashboard multi-brand:
  - `/brand/{owner_slug}`
- Jika satu owner memiliki lebih dari satu brand, response brand dashboard akan mengembalikan agregasi owner-level dengan `brands[]`.

File penting:

- `src/backend/vb.py`
- `main-vb/src/backend/vb.py`
- `main-vb/src/importer.py`
- `src/backend/db.py`
- `main-vb/src/backend/db.py`
- `database/migrations/015_vb_brand_owner.sql`

### D. Perubahan Frontend Dashboard VB

Perubahan public owner dashboard:

- Satu owner bisa menampilkan beberapa card brand dalam satu halaman.
- Toggle sekarang berada per brand, bukan di level owner.
- Card summary owner lama sudah dihapus.
- Label `Brand X dari Y` sudah dihapus.
- Baris metrik `Live Buka / Perlu Cek / Live Tutup` sudah dihapus dari card brand.
- Log aktivitas per-brand sudah dipindah menjadi satu panel aktivitas gabungan di level owner.
- Panel aktivitas owner mendukung:
  - filter chip per brand
  - default ringkas
  - tombol `Lihat semua aktivitas`

File penting:

- `src/backend/templates/brand_dashboard.html`
- `src/backend/static/css/styles.css`

Perubahan admin tab VB:

- Grouping owner sekarang berdasarkan owner asli dari sheet/import terbaru.
- Header owner lebih ringkas:
  - icon profile dihapus
  - nama owner + pill `Brand` dan `Store ID` satu baris
  - tombol `Link Dashboard` biru dengan teks putih

File penting:

- `src/backend/templates/admin_dashboard.html`
- `src/backend/static/css/styles.css`

### E. Testing Yang Sudah Dilakukan

- `uv run pytest tests/test_vb_owner_grouping.py tests/test_vb_pause_contract.py`
- `uv run pytest tests/test_frontend_routes.py`

Catatan:

- `tests/test_frontend_routes.py` sudah diperbarui untuk memastikan route public brand owner dashboard tetap ter-render.
- `tests/test_vb_owner_grouping.py` ditambahkan untuk mengunci perilaku owner grouping VB.

### F. Dokumentasi Yang Sudah Diselaraskan

- `DoD.md`
- `REPORT_VB_DEVELOPMENT.md`

Keduanya sudah disesuaikan dengan source VB aktif dan tidak lagi merujuk format/published sheet lama untuk jalur runtime yang dipakai saat ini.

---

## 1. Ringkasan Arsitektur Notifikasi

Sistem notifikasi dipisahkan secara tegas berdasarkan jenis bot dan platform tujuan:

| Parameter | Bot OC (`bot-oc`) | Virtual Brand (`bot-vb`) |
| :--- | :--- | :--- |
| **Media Utama** | WhatsApp Gateway (`bot-wa`) | Discord Webhook (`DISCORD_WEBHOOK_VB_URL`) |
| **Cakupan** | Outlet Reguler | Group Listing Virtual Brand |
| **Tipe Pesan** | Per-Outlet Event Notification | **Eksklusif Rekap Per-Group (Scenarios 1.1 - 1.6)** |
| **Individual Notif** | Aktif via Webhook `bot-wa` | **Bypassed / Disabled (No-Op Stub)** |
| **WhatsApp Notif** | Aktif via Webhook `bot-wa` | **Bypassed / Disabled (No-Op Stub)** |
| **Embed Footer** | `FoodMaster Bot Patrol Engine` | `FoodMaster Virtual Brand` |

---

## 2. Spesifikasi Notifikasi Discord Virtual Brand (`bot-vb`)

Seluruh notifikasi Discord di `main-vb/src/core/notifier.py` dipusatkan secara eksklusif via fungsi `send_discord_vb_group_summary` untuk 6 skenario utama:

### 2.1 🟢 VB Group Sukses Total Buka (`OPEN`)
- **Judul**: `🟢 VB GROUP BERHASIL DIBUKA BOT`
- **Warna Garis**: Hijau (`#2ECC71`)
- **Isi**:
  ```text
  VB Group: [Nama VB Group]
  Hasil: 5 Berhasil

  Berhasil Dibuka (5):
  ✅ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])
  ```

### 2.2 🔴 VB Group Sukses Total Tutup (`CLOSE / PAUSE`)
- **Judul**: `🔴 VB GROUP BERHASIL DITUTUP BOT`
- **Warna Garis**: Merah (`#E74C3C`)
- **Isi**:
  ```text
  VB Group: [Nama VB Group]
  Hasil: 5 Berhasil

  Berhasil Ditutup (5):
  ✅ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])
  ```

### 2.3 🟠 VB Group Sebagian Berhasil Buka (`PARTIAL OPEN`)
- **Judul**: `🟠 VB GROUP SEBAGIAN BERHASIL DIBUKA BOT`
- **Warna Garis**: Orange Alert (`#E67E22`)
- **Isi**:
  ```text
  VB Group: [Nama VB Group]
  Hasil: 3 Berhasil, 2 Gagal

  Berhasil Dibuka (3):
  ✅ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])

  Gagal Dibuka (2):
  ❌ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])
  ```

### 2.4 🟠 VB Group Sebagian Berhasil Tutup (`PARTIAL CLOSE`)
- **Judul**: `🟠 VB GROUP SEBAGIAN BERHASIL DITUTUP BOT`
- **Warna Garis**: Orange Alert (`#E67E22`)
- **Isi**:
  ```text
  VB Group: [Nama VB Group]
  Hasil: 3 Berhasil, 2 Gagal

  Berhasil Ditutup (3):
  ✅ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])

  Gagal Ditutup (2):
  ❌ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])
  ```

### 2.5 🔴 VB Group Gagal Total Buka (`ALL FAILED OPEN`)
- **Judul**: `🔴 VB GROUP GAGAL DIBUKA BOT`
- **Warna Garis**: Merah Alert (`#E74C3C`)
- **Isi**:
  ```text
  VB Group: [Nama VB Group]
  Hasil: 5 Gagal

  Gagal Dibuka (5):
  ❌ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])
  ```

### 2.6 🔴 VB Group Gagal Total Tutup (`ALL FAILED CLOSE`)
- **Judul**: `🔴 VB GROUP GAGAL DITUTUP BOT`
- **Warna Garis**: Merah Alert (`#E74C3C`)
- **Isi**:
  ```text
  VB Group: [Nama VB Group]
  Hasil: 5 Gagal

  Gagal Ditutup (5):
  ❌ [Nama Listing] — [Store ID] • [Link](https://shopee.co.id/universal-link/now-food/shop/[Store ID])
  ```

---

## 3. Microservice `bot-wa` (WhatsApp Gateway)

- **Struktur Direktori**: `bot-wa/` (Node.js + Baileys + Express).
- **Modul Independent**: Dapat dipindahkan dan dijalankan di VPS / Server lain.
- **Persistent Auth**: Sesi tersimpan di `./auth_info_baileys` / Docker Volume `wa_session_data`.
- **Anti-Ban Throttling**: Message Queue internal dengan delay pengiriman **1.5 detik** per pesan.
- **Keamanan**: Autentikasi header `X-API-Key`.

---

## 4. Panduan & Aturan Operasional Agent Server

1. **Zero-Downtime Execution**:
   - Dilarang mere-start service systemd atau container Docker jika hanya melakukan pembaruan notifikasi.
   - File Python di-mount via volume/disk sehingga perubahan langsung dibaca pada iterasi daemon berikutnya.
2. **Isolasi WhatsApp**:
   - `bot-vb` TIDAK AKAN PERNAH menembak `bot-wa`.
   - WhatsApp dikhususkan hanya untuk notifikasi merchant `bot-oc`.
3. **Environment Webhook**:
   - Set `DISCORD_WEBHOOK_VB_URL` untuk mengarahkan notifikasi Virtual Brand ke channel Discord khusus VB.
   - Fallback otomatis ke `DISCORD_WEBHOOK_URL` jika `DISCORD_WEBHOOK_VB_URL` belum diisi.
4. **Kebijakan Repository**:
   - Tidak melakukan `git push` tanpa instruksi eksplisit.
