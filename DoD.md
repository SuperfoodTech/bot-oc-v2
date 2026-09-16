# Definition of Done (DoD) - Optimalisasi Memori Lanjutan Tahap 1: CDP Request Blocking & Limit Renderer Process

Dokumen ini memuat kriteria keberhasilan (*Definition of Done*) untuk implementasi **Optimalisasi Memori Lanjutan Tahap 1** pada `bot-oc` dan `bot-vb`. Tahap ini berfokus pada **Pembatasan Proses Renderer Chrome** dan **Pemblokiran Network Request Non-Kritis via CDP (Chrome DevTools Protocol)** secara selektif tanpa mengganggu rendering DOM, API Shopee, atau kestabilan sesi bot.

---

## 1. Scope & Batasan Pekerjaan (Boundary Rules)

- [ ] **Ketersediaan Tuas Rollback**: Terverifikasi baseline versi 1.18.3 aman, dan rollback checkpoint siap diakses kapan saja.
- [ ] **Kepatuhan Paritas Browser (Strict Parity)**: File `src/core/browser.py` dan `main-vb/src/core/browser.py` **wajib tetap 100% identik (*byte-for-byte*, 0 diff)**.
- [ ] **Kepatuhan Paritas Worker (Strict Parity)**: File `main-bot/src/worker.py` dan `main-vb/src/worker.py` **tetap 100% identik (*byte-for-byte*, 0 diff)** (tidak ada modifikasi pada modul worker).
- [ ] **Isolasi Selektif (Safety First)**: Pemblokiran network via CDP dilarang keras menyentuh:
  - File JavaScript core Shopee (`*.js`)
  - File Stylesheet Shopee (`*.css`)
  - Endpoint REST / RPC API Shopee (`/api/*`)
  - Ikon/komponen yang esensial bagi selector navigasi DOM.

---

## 2. Kriteria Teknis Tahap 1

### A. Pembatasan Sub-Process Renderer Chrome
- [ ] **Flag Limit Renderer (`--renderer-process-limit=1`)**:
  - Menambahkan flag `--renderer-process-limit=1` pada `_init_driver` di `src/core/browser.py` dan `main-vb/src/core/browser.py`.
  - Menghemat ~50MB–80MB RAM dengan mengeliminasi alokasi proses renderer sekunder/iframe berlebih.
- [ ] **Flag Site Isolation Adjustment (`--disable-site-isolation-trials`)**:
  - Menambahkan flag `--disable-site-isolation-trials` untuk mencegah Chromium membuat proses isolasi terpisah pada cross-origin origin internal.

### B. Pemblokiran Network Aset Non-Kritis via CDP
- [ ] **Inisialisasi CDP Network Interception**:
  - Mengaktifkan domain jaringan CDP melalui `driver.execute_cdp_cmd("Network.enable", {})` saat driver diinisialisasi di `_init_driver()`.
- [ ] **Blacklist URL Non-Esensial**:
  - Memasang aturan `Network.setBlockedURLs` dengan pola spesifik:
    - Font web dekoratif: `*.woff`, `*.woff2`, `*.ttf`, `*.eot`
    - Tracker/telemetri pihak ketiga: `*google-analytics*`, `*doubleclick*`, `*facebook*`, `*sensorsdata*`, `*hotjar*`
- [ ] **Graceful Degradation / Exception Handling**:
  - Pemanggilan CDP dibungkus dalam blok `try...except` agar jika versi Chromium/driver mengalami isu CDP, inisialisasi browser tetap berjalan lancar tanpa mengalami fatal crash.

---

## 3. Pengujian & Verifikasi (Testing Plan)

- [ ] **Verifikasi Paritas File**:
  - `cmp src/core/browser.py main-vb/src/core/browser.py` -> Wajib menghasilkan **0 diff**.
- [ ] **Syntax & Import Validation**:
  - `.venv/bin/python3 -m py_compile src/core/browser.py main-vb/src/core/browser.py` -> Bebas dari error sintaks.
- [ ] **Validasi Navigasi & Selector DOM**:
  - Memastikan otomasi login/session load, merchant switch, dan tombol dialog buka/tutup toko tetap dapat teridentifikasi dan diklik normal tanpa kendala elemen hilang.
- [ ] **Dokumentasi & Versi**:
  - Mencatat update pada dokumen rilis `update/1.18.4.md`.
  - Memperbarui baseline rilis pada `.agents/AGENTS.md`.
