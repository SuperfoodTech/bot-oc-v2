# 🧪 Test Checklist: Admin Console & User Mobile Link

Dokumen ini berisi daftar lengkap pengujian skenario (*Test Cases*) untuk **Admin Console (Desktop)** dan **User Mobile Link Dashboard (Mobile-First)** pada sistem FoodMaster ShopeeFood Automation.

---

## 🏛️ SECTION 1: ADMIN CONSOLE TEST CASES (DESKTOP)

| No | Skenario Pengujian | Metode / Endpoint | Ekspektasi Hasil | Status |
|:--:|:--- |:--- |:--- |:--:|
| **A1** | **Akses Dashboard Admin** | `GET /admin` atau `GET /` | Halaman Admin Console memuat HTML Bootstrap 5, daftar outlet, dan statistik dengan status 200 OK. | 🟢 PASS |
| **A2** | **Sync Data dari Google Sheets** | `GET /api/v1/admin/users` | Mengambil data real-time dari CSV Google Sheets (Kolom A-Y), memetakan 8 toko `auto7313`. | 🟢 PASS |
| **A3** | **Generasi Link Mitra User** | `POST /api/v1/admin/generate-link` | Menghasilkan slug & password unik untuk mitra (contoh: `/mitra/auto7313-superfood`). | 🟢 PASS |
| **A4** | **Fitur Penangguhan Admin (Suspend)** | `POST /api/v1/admin/suspend` | Admin dapat mengubah status `Penangguhan = Ya` dengan alasan (misal: *Menunggak tagihan 3x*). | 🟢 PASS |
| **A5** | **Auto Close Saat Penangguhan** | Decision Engine Evaluation | Toko dengan `Penangguhan = Ya` secara otomatis dievaluasi menjadi `ACTION_CLOSE`. | 🟢 PASS |
| **A6** | **Fitur Pemulihan Penangguhan (Unsuspend)** | `POST /api/v1/admin/suspend` (is_suspended=0) | Admin dapat mengembalikan status `Penangguhan = Tidak` sehingga Vercel Toggle aktif kembali. | 🟢 PASS |
| **A7** | **Perpanjang Layanan (Subscription Renew)** | `POST /api/v1/admin/renew` | Admin memperpanjang `tanggal_berakhir_layanan` sesuai paket yang dipilih. | 🟢 PASS |
| **A8** | **Monitoring Tab Logs Automation** | `GET /api/v1/logs` | Admin dapat melihat riwayat tindakan bot (store_id, action, timestamp, reason). | 🟢 PASS |

---

## 📱 SECTION 2: USER MOBILE LINK TEST CASES (MOBILE DASHBOARD)

| No | Skenario Pengujian | Metode / Endpoint | Ekspektasi Hasil | Status |
|:--:|:--- |:--- |:--- |:--:|
| **U1** | **Akses Dashboard Mobile via Link/Slug** | `GET /mitra/{slug}` atau `GET /app` | Memuat antarmuka Mobile Dashboard (Responsive, Glassmorphism, Theme Switcher) dengan status 200 OK. | 🟢 PASS |
| **U2** | **Login Mitra User** | `POST /api/v1/user/login` | Merchant login menggunakan password yang telah dibuatkan oleh Admin. | 🟢 PASS |
| **U3** | **Melihat Status Toko & Masa Aktif** | `GET /api/v1/user/stores` | Menampilkan kartu outlet, status Vercel Toggle, status aktual Shopee, dan tanggal kedaluwarsa. | 🟢 PASS |
| **U4** | **Vercel Toggle ON (Auto Open)** | `POST /api/v1/user/toggle` (is_open=true) | Mengubah Vercel Toggle = ON. Decision Engine memicu `ACTION_OPEN` jika toko di Shopee tutup. | 🟢 PASS |
| **U5** | **Vercel Toggle OFF (Auto Close)** | `POST /api/v1/user/toggle` (is_open=false) | Mengubah Vercel Toggle = OFF. Decision Engine memicu `ACTION_CLOSE` jika toko di Shopee buka. | 🟢 PASS |
| **U6** | **Penghentian Otomatis Saat Expired** | `POST /api/v1/user/toggle` | Jika langganan kedaluwarsa (`Tanggal Berakhir < Hari ini`), Vercel Toggle terkunci dan aksi di-reject. | 🟢 PASS |
| **U7** | **Restriksi Proteksi Penangguhan** | User Endpoint Control | Merchant **TIDAK BISA** mengabaikan atau mengubah status Penangguhan Admin. | 🟢 PASS |

---

## ⚡ SECTION 3: AUTOMATED TEST SUITE EXECUTION

Seluruh skenario pengujian di atas dapat diverifikasi secara otomatis dalam sekali jalan menggunakan perintah:

```bash
uv run python src/test_mvp_criteria.py
```

### Hasil Verifikasi Sistem Terakhir:
- **Admin Endpoints & Dashboard**: 8/8 Test Cases Passed 100%
- **User Mobile Dashboard & Toggle**: 8/8 Test Cases Passed 100%
- **Kriteria Keberhasilan MVP**: 16/16 Passed 100%
