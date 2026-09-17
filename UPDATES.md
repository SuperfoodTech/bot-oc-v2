# Knowledge Transfer & Alignment Guide - Notification Architecture (`bot-oc` & `bot-vb`)

Dokumen ini berisi rangkuman arsitektur, spesifikasi notifikasi, dan aturan operasional untuk alignment antar agent/server.

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
