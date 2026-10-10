# Implementation Plan & Definition of Done (DoD)

## 📌 Judul Rencana
**Penyelarasan 1:1 Tri-State Status Operasional (Buka, Tutup Sementara, Di Luar Jam Operasional) dan Widget Card Interaktif Target Force Open (Agency & Virtual Brand)**
**Target Versi:** `v1.35.0`

---

## 🎯 1. Objektif & Latar Belakang Masalah

### A. Latar Belakang Masalah (Root Cause)
1. **Pencampuran Status Tutup:**
   - Saat ini di tab **Agency**, widget card ringkasan hanya memiliki 3 kartu: `Total Outlet`, `Sedang Buka`, dan `Sedang Tutup`.
   - Di tab **Virtual Brand (VB)**, widget card ringkasan grup hanya memiliki 3 kartu: `Total Grup VB`, `Grup Aktif`, dan `Grup Nonaktif`.
   - Di kedua tab tersebut, status **Tutup Sementara / Pause (Merah)** tercampur aduk ke dalam satu angka dengan status **Di Luar Jam Operasional (Abu-abu / Tutup Alami Shopee)**.
2. **Kendala Kritis Operasional:**
   - Ketika merchant mematikan toggle (misal saat jam makan siang, dapur overload, atau hujan lebat) lalu **lupa menyalakan kembali**, toko/brand tersebut tenggelam di antara puluhan toko lain yang memang belum/sudah selesai jam operasionalnya.
   - Admin dan tim CS kehilangan visibilitas cepat toko mana yang sedang kehilangan omzet (*lost sales*) dan harus men-scroll tabel secara manual satu per satu untuk mencari baris yang bertombol merah.
3. **Kebutuhan Solusi:**
   - Memisahkan status menjadi **3 State Deterministik**:
     1. **Buka (Toggle ON - Hijau)**
     2. **Tutup Sementara / Pause (Toggle OFF - Merah)** ⚠️ *(Target Utama Force Open)*
     3. **Di Luar Jam Operasional (Toggle Disable - Abu-abu)**
   - Menghadirkan **Widget Card 4-Kolom** yang presisi dan interaktif (*Click-to-Filter*) baik di dashboard **Agency** maupun **Virtual Brand**.

---

## 🧭 2. Matrix Definisi Tri-State Status Operasional

| Kategori Status | State Visual Toggle | Kondisi Jam Operasional | Logika Sistem (`stateContext`) | Tindakan Admin / CS |
| :--- | :--- | :--- | :--- | :--- |
| **1. Buka (Open)** | **Toggle ON**<br>*(Hijau `#15803d`)* | Dalam Jam Operasional (`within_operating_schedule == true`) | `desiredState == 'OPEN'`, toggle switch aktif di posisi kanan (`checked`). | Normal. Toko beroperasi aktif dan dijaga bot patroli agar tidak tutup mendadak di Shopee. |
| **2. Tutup Sementara (Paused)** | **Toggle OFF**<br>*(Merah `#dc2626`)* | **Dalam Jam Operasional** (`within_operating_schedule == true`) | `desiredState == 'PAUSE'` / manual off, toggle switch di posisi kiri (`unchecked`), tetapi **elemen aktif / pointer clickable**. | ⚠️ **TARGET FORCE OPEN!** Toko seharusnya buka sekarang tapi dimatikan. Potensi mitra lupa menyalakan kembali. Admin dapat mengklik toggle untuk langsung *Force Open / Resume*. |
| **3. Di Luar Jam Operasional (Closed)** | **Toggle Disable**<br>*(Abu-abu `#9ca3af`)* | **Di Luar Jam Operasional** (`within_operating_schedule == false`) / Jadwal Khusus Tutup | `display_toggle_disabled == true` / `botPhase == 'WAITING_SCHEDULE'` / `SPECIAL_HOURS`, toggle switch di kiri dan **terkunci / disabled**. | Normal / Alami. Jam kerja resmi toko di Shopee memang belum mulai atau sudah berakhir. Bot mengunci toggle demi mencegah order bocor di luar jam operasional. Tidak perlu intervensi. |

---

## 🏗️ 3. Komponen yang Terdampak & Rencana Arsitektur Perubahan

### A. Tab Agency / Operasional (`src/backend/templates/admin_tab_operasional.html`)
1. **Widget Card Header (`.stats-grid`):**
   - Mengubah struktur dari 3 kartu menjadi **4 kartu metrik presisi**:
     1. `metricTotal`: **Total Outlet** (Netral)
     2. `metricOpen`: **Sedang Buka** (Hijau - Toggle ON)
     3. `metricPaused`: **Tutup Sementara** (Merah / Oranye - Toggle OFF) ⚠️ *(Highlight: Target Force Open)*
     4. `metricClosed`: **Di Luar Jadwal** (Abu-abu - Toggle Disable)
   - Setiap kartu metrik dilengkapi atribut interaktif `role="button"` dan event listener `onclick="setAgencyFilterFromCard(status)"` (*Click-to-Filter*).
2. **Mobile Summary Strip (`#mobileSummaryStrip`):**
   - Menyelaraskan 4 segmen tombol ringkasan mobile: `Semua`, `Buka`, `Pause (Merah)`, dan `Di Luar Jadwal (Abu-abu)`.
3. **Filter Dropdown Status Desktop & Mobile (`#statusFilter` & `#mobileStatusFilter`):**
   - Menambahkan opsi filter lengkap:
     - `""`: Semua status
     - `"open"`: Sedang Buka (Toggle ON)
     - `"paused"`: Tutup Sementara (Toggle OFF)
     - `"closed"`: Di Luar Jam Operasional (Toggle Disable)

### B. Tab Virtual Brand (`src/backend/templates/admin_tab_vb.html`)
1. **Widget Card Brand (`#vbStatsGrid` & `renderVBStats`):**
   - Menyelaraskan kartu metrik grup VB menjadi 4 kartu grup presisi:
     1. **Total Grup VB** (Netral)
     2. **Grup Buka (ON)** (Hijau - `brand.vbToggleState === 'open'`)
     3. **Grup Pause (OFF)** (Merah - `brand.vbToggleState === 'paused'`) ⚠️ *(Target Force Open)*
     4. **Grup Di Luar Jadwal (Closed)** (Abu-abu - `brand.vbToggleState === 'closed'`)
   - Mempertahankan kartu rincian Store ID: `Total Store ID`, `Store Live Buka`, dan `Store Live Tutup` dengan visual counter yang rapi.
   - Menjadikan kartu grup interaktif (*Click-to-Filter*): Mengklik kartu *Grup Pause* seketika menyetel filter `#vbStatusFilter` ke `PAUSE` dan memfilter list brand.
2. **Filter Status Grup VB (`#vbStatusFilter` & `#mobileVbStatusFilter`):**
   - Menjaga sinkronisasi 1:1 antara opsi filter (`OPEN`, `PAUSE`, `CLOSED`) dengan kartu metrik di atasnya.

### C. Backend Engine & Controller (`src/backend/db.py`, `admin_dashboard.html`)
1. **Status Categorization Function (`getAdminStatusCategory`):**
   - Mengembalikan 3 kategori deterministik: `'open'`, `'paused'`, dan `'closed'` (di luar jam operasional).
   - Memperbarui `updateAgencyStatCards(stores)` untuk menghitung counter `metricTotal`, `metricOpen`, `metricPaused`, dan `metricClosed`.
2. **Table Filtering Logic (`filterTable` & `matchesStatusFilter`):**
   - Memastikan saat filter `'paused'` dipilih, hanya baris outlet dengan `toggleState === 'paused'` yang tampil.
   - Memastikan saat filter `'closed'` dipilih, hanya baris outlet dengan `toggleState === 'closed'` (toggle disable) yang tampil.
3. **VB Brand Views Calculation (`buildVbBrandViews` & `renderVBStats`):**
   - Menghitung `groupsOpen`, `groupsPaused`, dan `groupsClosed` berdasarkan `brand.vbToggleState` yang sudah valid.

### D. Visual Styling & Interaktivitas UI (`src/backend/static/css/styles.css`)
1. **Styling Kartu Baru `.metric-card-paused`:**
   - Aksen border dan icon merah/oranye senada dengan status toggle pause (`#dc2626` / `#ef4444`).
   - Hover state dinamis dan pointer cursor yang intuitif untuk mengindikasikan kartu dapat diklik (*Click-to-Filter*).
2. **Active State Indikator:**
   - Memberikan highlight visual kartu yang sedang aktif memfilter tabel (misal border glow atau outline tebal).

---

## ✅ 4. Definition of Done (DoD) Checklist

### A. Tab Agency (Operasional Outlets)
- [x] Widget card di header memiliki 4 kartu: **Total Outlet**, **Sedang Buka (Hijau)**, **Tutup Sementara / Pause (Merah)**, dan **Di Luar Jam Operasional (Abu-abu)**.
- [x] Angka pada kartu **Tutup Sementara (Merah)** hanya menghitung outlet yang berada dalam jam operasional tapi toggle-nya OFF / paused.
- [x] Angka pada kartu **Di Luar Jam Operasional (Abu-abu)** hanya menghitung outlet yang toggle-nya disabled / outside schedule / special hours.
- [x] Mengklik kartu **Tutup Sementara (Merah)** otomatis memfilter tabel sehingga HANYA menampilkan outlet yang sedang Pause (siap di-Force Open).
- [x] Dropdown filter desktop (`#statusFilter`) dan mobile sheet (`#mobileStatusFilter`) memiliki opsi: *Semua Status*, *Sedang Buka*, *Tutup Sementara*, dan *Di Luar Jam Operasional*.
- [x] Mobile summary strip (`#mobileSummaryStrip`) memiliki 4 segmen yang berfungsi responsif.

### B. Tab Virtual Brand (VB)
- [x] Widget card grup VB di `#vbStatsGrid` memiliki pembagian yang selaras: **Total Grup VB**, **Grup Buka (ON)**, **Grup Pause (OFF)**, dan **Grup Di Luar Jadwal (Closed)**.
- [x] Angka pada kartu **Grup Pause (OFF)** hanya menghitung brand dengan `vbToggleState === 'paused'`.
- [x] Angka pada kartu **Grup Di Luar Jadwal (Closed)** hanya menghitung brand dengan `vbToggleState === 'closed'`.
- [x] Mengklik kartu **Grup Pause** otomatis memfilter tabel brand ke status `PAUSE`.
- [x] Filter dropdown status grup VB (`#vbStatusFilter` & `#mobileVbStatusFilter`) sinkron sempurna dengan kartu metrik.

### C. Konsistensi & Integritas Operasional
- [x] Visual toggle di tabel (Hijau untuk Buka, Merah untuk Pause/Tutup Sementara, Abu-abu untuk Di Luar Jam) tetap terjaga 100% konsisten.
- [x] Tindakan klik toggle pada outlet yang berstatus Tutup Sementara (Merah) tetap mengeksekusi Resume / Buka Toko (*Force Open*) secara mulus.
- [x] Perubahan kode murni non-bot (frontend/web backend), sehingga deploy dilakukan dengan Zero-Downtime Deployment (`docker compose build web && docker compose up -d --no-deps web`).
- [x] Bot patroli Selenium daemon (`fm-bot`) tetap berjalan aktif tanpa interupsi.
