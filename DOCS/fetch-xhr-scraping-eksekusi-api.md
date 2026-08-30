# Dokumentasi Fetch/XHR untuk Scraping via API dan Eksekusi via API

## Ringkasan

Di project ini, istilah "scraping" untuk Shopee Food tidak berarti membaca HTML sebagai jalur utama. Jalur resminya adalah menarik data dari request kategori `Fetch/XHR` yang dipakai halaman partner Shopee sendiri, lalu mengeksekusinya dari browser Selenium yang sudah login.

Istilah `Fetch/XHR` di dokumen ini mengikuti kategori pada DevTools browser. Implementasi aktif di kode memakai `fetch(...)`, bukan `XMLHttpRequest` manual.

Implementasi aktif ada di:

- `src/shopee/store_status.py`
- `main-bot/src/worker.py`

Browser menjadi komponen penting karena request membutuhkan sesi login aktif, cookie domain Shopee, dan konteks origin `https://partner.shopee.co.id`.

## Cakupan kemampuan

| Kemampuan | Endpoint | Method | Fungsi di kode | Tujuan |
| --- | --- | --- | --- | --- |
| Live status read | `https://foody.shopee.co.id/api/seller/store` | `GET` | `get_actual_store_status` | Ambil status outlet real-time |
| Regular hours read | `https://foody.shopee.co.id/api/seller/store/regular-hours` | `GET` | `get_regular_hours` | Ambil jadwal reguler outlet |
| Open action | `https://foody.shopee.co.id/api/seller/store/opening-status/action/open?store_id={store_id}` | `POST` | `open_store_action` | Buka outlet via API |
| Pause action | `https://foody.shopee.co.id/api/seller/store/opening-status/action/pause?store_id={store_id}` | `POST` | `pause_store_action` | Pause outlet via API |

## Kenapa dijalankan dari browser

Jalur ini sengaja tidak memakai `requests` biasa sebagai implementasi utama karena:

1. Request harus membawa cookie sesi yang sudah aktif di browser, termasuk konteks `shopee_tob_token` dan `shopee_tob_entity_id`.
2. Request berjalan sebagai same-site lintas origin dari `partner.shopee.co.id` ke `foody.shopee.co.id`, sehingga `credentials: 'include'` wajib dipakai.
3. Header seperti `x-sap-ri` dan `x-sap-sec` muncul pada request browser dan nilainya bersifat sesi-spesifik.
4. Store context dibawa oleh kombinasi URL business-hours aktif, cookie sesi, dan `store_id` target.

Karena itu implementasi resmi memakai `driver.execute_async_script(...)` yang mengeksekusi `fetch(...)` langsung di dalam halaman partner Shopee.

## Prasyarat sebelum fetch/XHR dipakai

Sebelum endpoint read maupun action dipanggil, bot selalu memastikan:

1. Browser sudah login ke partner Shopee.
2. Merchant portal yang aktif di browser sudah benar.
3. Driver sudah masuk ke halaman:

```text
https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}
```

4. Halaman sudah terhidrasi dan keyword UI seperti `jam operasional`, `tutup outlet`, atau `buka outlet` sudah terbaca.

Semua logika itu ditangani oleh `ensure_business_hours_page(driver, store_id)`.

## Pola scraping via API

### 1. Live status outlet

Fungsi: `get_actual_store_status(driver, store_id)`

Pola request:

```javascript
fetch('https://foody.shopee.co.id/api/seller/store', {
  method: 'GET',
  credentials: 'include',
  headers: { Accept: 'application/json, text/plain, */*' }
})
```

Karakteristik implementasi:

1. Dijalankan melalui `execute_async_script`.
2. Memakai `AbortController` timeout 5 detik.
3. Retry maksimal 2 kali.
4. Bila API tidak mengembalikan `code == 0`, bot fallback ke pembacaan badge DOM sebagai jalur read-only cadangan.

Mapping status yang dipakai:

- `OPEN` jika `display_opening_status == 2` atau `order_enabled == 1`, dan `pause_start_time == 0`.
- `CLOSED` untuk kondisi selain itu di response live API.
- Di level worker, status live kemudian dinormalisasi lagi menjadi `ON`, `PAUSE`, atau `CLOSED` berdasarkan `pause_start_time`.

Artefak referensi:

- `DOCS/store-header.txt`
- `DOCS/store-response.json`

### 2. Regular hours outlet

Fungsi: `get_regular_hours(driver, store_id)`

Pola request:

```javascript
fetch('https://foody.shopee.co.id/api/seller/store/regular-hours', {
  method: 'GET',
  credentials: 'include',
  headers: { Accept: 'application/json, text/plain, */*' }
})
```

Karakteristik implementasi:

1. Timeout 5 detik.
2. Retry maksimal 2 kali.
3. Hanya dianggap berhasil bila `code == 0`.
4. Response `regular_hours` lalu dinormalisasi oleh worker menjadi format jam baca manusia `HH:MM-HH:MM` per hari.

Artefak referensi:

- `DOCS/reguler-hours-header.txt`
- `DOCS/reguler-hours-response.json`

## Pola eksekusi via API

Eksekusi aksi outlet tidak dilakukan dengan klik tombol UI sebagai jalur utama. Worker memanggil API action langsung setelah decision engine memutuskan outlet harus dibuka atau dipause.

Alur eksekusinya:

1. `main-bot/src/worker.py` menjalankan evaluasi rule per outlet.
2. Bila hasilnya `ACTION_OPEN` atau `ACTION_CLOSE`, worker memanggil `execute_outlet_shopee_action(...)`.
3. Fungsi itu meneruskan eksekusi ke `open_store_action(...)` atau `pause_store_action(...)`.
4. Setelah action sukses, worker tidur 1.5 detik lalu memanggil ulang live API untuk verifikasi pasca-eksekusi.
5. Status hasil verifikasi disimpan kembali ke database melalui `db.update_shopee_actual_status(...)`.

### 1. Action open

Fungsi: `open_store_action(driver, store_id, merchant_id='14367488')`

Pola request:

```javascript
fetch(`https://foody.shopee.co.id/api/seller/store/opening-status/action/open?store_id=${store_id}`, {
  method: 'POST',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/plain, */*'
  },
  body: JSON.stringify({
    store_id: String(store_id)
  })
})
```

Kriteria sukses:

- Response JSON mengandung `code == 0`.

Artefak referensi:

- `DOCS/open outlet/open-header.txt`
- `DOCS/open outlet/open-payload,txt`
- `DOCS/open outlet/open-response.json`

### 2. Action pause

Fungsi: `pause_store_action(driver, store_id, merchant_id='14367488', pause_duration_minutes=1440, pause_end_time_ms=None)`

Pola request:

```javascript
const now = Date.now();
const end = pause_end_time_ms ?? (now + pause_duration_minutes * 60 * 1000);

fetch(`https://foody.shopee.co.id/api/seller/store/opening-status/action/pause?store_id=${store_id}`, {
  method: 'POST',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/plain, */*'
  },
  body: JSON.stringify({
    pause_start_time: now,
    pause_end_time: end,
    store_id: Number(store_id)
  })
})
```

Catatan implementasi:

1. Bila `pause_end_time_ms` tersedia dari database, nilai itu diprioritaskan.
2. Bila tidak ada, bot memakai durasi default `pause_duration_minutes`.
3. Query parameter tetap menyertakan `store_id` meskipun body juga membawa data pause.

Kriteria sukses:

- Response JSON mengandung `code == 0`.

Artefak referensi:

- `DOCS/pause outlet/pause-header.txt`
- `DOCS/pause outlet/pause-payload.txt`
- `DOCS/pause outlet/pause-response.json`

## Cara capture ulang request Fetch/XHR dari browser

Jika ingin memperbarui dokumentasi header, payload, atau response:

1. Login ke partner Shopee dengan akun yang memang dipakai bot.
2. Buka halaman business-hours untuk `store_id` target.
3. Buka DevTools -> tab Network.
4. Filter request ke kategori `Fetch/XHR`.
5. Untuk endpoint read, refresh halaman atau tunggu panel business-hours memuat data.
6. Untuk endpoint action, klik aksi di UI atau biarkan bot mengeksekusi action.
7. Salin `Request URL`, `Request Method`, header penting, payload, dan response JSON.
8. Simpan ke file referensi di folder `DOCS/`.

## Batasan dan guardrail

1. Ini bukan public API yang bisa diandalkan tanpa sesi browser aktif.
2. Nilai cookie dan header security di file `DOCS/*header*.txt` bersifat sensitif serta bisa kedaluwarsa; gunakan sebagai referensi struktur request, bukan literal value permanen.
3. Jalur fallback DOM hanya dipakai untuk pembacaan status, bukan untuk action open/pause.
4. Parameter `merchant_id` ada di signature fungsi untuk konteks pemanggilan worker, tetapi request action yang aktif saat ini bergantung pada sesi browser dan `store_id` target.

## Ringkasannya

Kemampuan bot saat ini bisa dibagi dua:

1. Read capability: menarik status live dan regular hours lewat endpoint `Fetch/XHR` Shopee yang sudah terautentikasi.
2. Execute capability: membuka dan mempause outlet lewat endpoint action API tanpa klik UI sebagai jalur utama.

Seluruh jalur itu bergantung pada browser Selenium yang sudah login dan berada di konteks halaman business-hours yang benar.
