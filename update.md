# Dokumentasi Perbaikan: Resolusi `Failed to fetch` pada Mode Headless Chrome

**Tanggal**: 17 Agustus 2026  
**Komponen**: `src/core/browser.py`, `main-bot/src/worker.py`, `src/backend/worker.py`, `.env`  
**Status**: ✅ Resolved & Verified  

---

## 1. Ringkasan Masalah

Saat menjalankan bot patroli Shopee dalam mode **Headless** (`HEADLESS=true`), muncul peringatan fallback pada eksekusi XHR API:

```log
⚠️ [LIVE STORE API FALLBACK] Respon API /api/seller/store bukan 0: {'code': -1, 'msg': 'Failed to fetch'}. Menjalankan pengecekan DOM...
```

Namun, saat mode **GUI** (`HEADLESS=false`) diaktifkan, eror tersebut **tidak pernah terjadi** dan API mengembalikan respon sukses `{"code": 0, "data": {...}}`.

---

## 2. Analisis Penyebab Utama (Root Cause)

1. **Headless Chrome User-Agent Detection**:
   Secara default, Chrome dalam mode `--headless` atau `--headless=new` mengirimkan header `User-Agent` yang mengandung identifier `HeadlessChrome` (contoh: `Mozilla/5.0 ... HeadlessChrome/125.0...`).
2. **Detection Flag `navigator.webdriver`**:
   Browser otomatisasi Selenium menetapkan properti JavaScript `navigator.webdriver = true`.
3. **Pemblokiran Cross-Origin XHR oleh Shopee / Cloudflare WAF**:
   Ketika skrip mengeksekusi `fetch('https://foody.shopee.co.id/api/seller/store')` dari domain dashboard (`https://partner.shopee.co.id`), request tersebut bersifat *Cross-Origin*. Cloudflare / Shopee WAF mendeteksi kata `HeadlessChrome` dan properti `navigator.webdriver`, lalu menolak preflight CORS request.
4. **Exception `TypeError: Failed to fetch`**:
   Kegagalan koneksi CORS pada level JavaScript browser melemparkan exception `TypeError: Failed to fetch` yang ditangkap sebagai `{'code': -1, 'msg': 'Failed to fetch'}`.

---

## 3. Perubahan Kode (Solusi Terapan)

### A. Stealth Anti-Bot & User-Agent Spoofing pada [`src/core/browser.py`](file:///home/akbarhann/project/bot-oc/src/core/browser.py#L693-L733)

Telah ditambahkan konfigurasi User-Agent Desktop standar, penyesuaian resolusi viewport, serta penonaktifan throttling background pada fungsi `_init_driver()`:

```python
if headless:
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
else:
    options.add_argument("--start-maximized")
```

### B. Menyembunyikan `navigator.webdriver` via Chrome DevTools Protocol (CDP)

Pada saat WebDriver diinstansiasi, ditambahkan skrip CDP yang dieksekusi sebelum dokumen dimuat:

```python
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
except Exception:
    pass
```

### C. Sentralisasi Pengaturan Headless via `.env`

Seluruh variabel hardcoded `HEADLESS` dan argumen `headless=...` di skrip Python lainnya telah dihapus agar mengacu pada variabel di [`.env`](file:///home/akbarhann/project/bot-oc/.env):

- **File `.env`**:
  ```env
  HEADLESS=true
  ```
- **Pembersihan pada skrip**:
  - `main-bot/src/worker.py`
  - `src/backend/worker.py`
  - `main-bot/src/daemon.py`
  - `open_dashboard.py`
  - `scripts/open_dashboard_auto7313.py`
  - `scripts/test_business_hours_flow.py`
  - `main-bot/src/test_bot_chrome_profile_login.py`

---

## 4. Hasil Verifikasi

Setelah penerapan solusi stealth dan sentralisasi `.env`, pengujian daemon cycle pada mode Headless menunjukkan hasil 100% sukses:

```log
20:03:55 | INFO     | 🌐 [BROWSER] Launching (headless=True, attempt=1/3)...
20:04:04 | INFO     | ✅ [SESSION] Browser is already logged in.
20:04:08 | INFO     | 🏬 [MERCHANT GROUP] Processing 1 outlets for Merchant Portal: 'SuperFood'...
20:04:10 | INFO     |   ✅ [BUSINESS HOURS CONFIRMED] Target Store 21708900 TERDETEKSI & TER-LOAD SEMPURNA!
20:04:11 | INFO     |   ✅ [IN-BROWSER XHR SUCCESS] ACTION_OPEN executed successfully for Store 21708900.
```

- Eror `Failed to fetch` **berhasil diatasi sepenuhnya**.
- XHR Direct API `/api/seller/store` mengembalikan respon `code: 0` secara instan dalam mode Headless.
