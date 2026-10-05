# Dokumentasi Teknis Penarikan Data Pesanan Shopee (/trx)

Dokumentasi ini menjelaskan secara komprehensif arsitektur, cara kerja, alur data, dan mekanisme autentikasi dari fitur slash command Discord **/trx** yang digunakan untuk menarik response JSON mentah langsung dari Shopee Food Seller Web API.

---

## 1. Ringkasan & Tujuan Fitur

- **Tujuan:** Menarik data detail pesanan (*order details*) secara instan dalam format JSON mentah langsung dari backend Shopee Food tanpa proses parsing manual yang memotong field penting.
- **Waktu Eksekusi:** **< 1 Detik** per pesanan (jauh lebih cepat dibanding unduhan via UI browser yang memakan waktu 15–40 detik).
- **Hasil:**
  - File JSON mentah tersimpan di server direktori:
    ```bash
    /home/fat-data/shopee/{tanggal_folder}/raw_orders/{nama_merchant}_{order_id}.json
    ```
  - Discord bot mengirimkan Embed Review konfirmasi beserta file attachment `.json` mentah untuk diunduh langsung oleh user.

---

## 2. Struktur Komponen & Berkas Terkait

| Komponen | Path File | Fungsi Utama |
| :--- | :--- | :--- |
| **Discord Slash Command** | [`discord-bot-weekly/src/commands/Modals/trx.js`](file:///root/home/akbar/weekly/discord-bot-weekly/src/commands/Modals/trx.js) | Menangani interaksi Discord (`/trx`), dropdown merchant, pop-up modal input tanggal/order ID, dan pengiriman embed/attachment. |
| **Backend API Fetcher** | [`agency/shopee/fetch_single_order.py`](file:///root/home/akbar/weekly/agency/shopee/fetch_single_order.py) | Skrip Python mandiri untuk menembak endpoint Shopee API, menginjeksi MID merchant, memvalidasi authority, dan menyimpan raw JSON. |
| **Master Merchants Cache** | [`agency/shopee/data/master_merchants_cache.csv`](file:///root/home/akbar/weekly/agency/shopee/data/master_merchants_cache.csv) | Database master outlet/merchant yang memetakan Nama Merchant ke **Merchant ID (MID)** dan **Store ID (SID)**. |
| **Session & Token Storage** | [`agency/data/session.json`](file:///root/home/akbar/weekly/agency/data/session.json) | Menyimpan `shopee_tob_token` aktif akun master (`allvbadmin`) dan cookies sesi partner. |
| **Service Bot (Systemd)** | `/etc/systemd/system/weekly-discord-bot.service` | Service daemon Node.js yang menjalankan Discord bot secara background & persisten. |

---

## 3. Diagram Alur Kerja (Workflow)

```
[User di Discord]
       │
       ▼ Ketik /trx
[Discord Bot (trx.js)]
       │
       ├─► 1. Ambil list 71 merchant Shopee (Google Sheets / Cache CSV)
       │      (Menampilkan nama bersih tanpa nomor portal, mencakup status Live & Pending)
       │
       ▼ User memilih Nama Merchant (misal: "NASI Grg DAN BAKMIE ROSE_")
[Modal Pop-up Discord]
       │
       ├─► User mengisi secara manual:
       │     - Tanggal Mulai   (DD-MM-YYYY, misal: 21-09-2026)
       │     - Tanggal Selesai (DD-MM-YYYY, misal: 27-09-2026)
       │     - Order ID Shopee (misal: 3286071779363840692)
       │
       ▼ Klik Kirim / Submit
[Python Backend (fetch_single_order.py)]
       │
       ├─► 2. Resolusi Merchant ID:
       │      Pencarian ke master_merchants_cache.csv:
       │      "NASI Grg DAN BAKMIE ROSE_" ──► MID: 1146482, Store ID: 1148112
       │
       ├─► 3. Virtual Switch Merchant & Injeksi Cookie:
       │      Cookie: shopee_tob_token = <master_token>
       │      Cookie: shopee_foody_mid = "1146482"
       │      Cookie: shopee_tob_entity_id = ""
       │
       ├─► 4. Direct HTTP Request ke Shopee Seller API:
       │      GET https://foody.shopee.co.id/api/seller/web/orders/{order_id}?feature_flag=64
       │
       ├─► 5. Server Shopee merespons: Status 200 OK, code: 0, msg: "success"
       │
       ▼ Simpan File ke Server Directory:
       /home/fat-data/shopee/2026-09-21_to_2026-09-27/raw_orders/NASI_Grg_DAN_BAKMIE_ROSE_3286071779363840692.json
       │
       ▼ Kirim ke Discord:
[Embed Review + File Attachment .json]
```

---

## 4. Analisis Teknis: Mengapa Eksekusi Sangat Cepat (< 1 Detik)?

Kecepatan instan ini dicapai melalui optimasi arsitektural:

### A. Bypass Overhead Browser (Zero DOM Rendering)
Biasanya, otomatisasi scraping membuka Chromium/Chrome headless:
1. Membuka browser: ~3-5 detik.
2. Memuat aset JavaScript, CSS, dan DOM portal partner: ~5-10 detik.
3. Mencari elemen dropdown dan simulasi klik switch toko: ~4-8 detik.
4. Menunggu network trigger: ~5-10 detik.
*Total waktu browser tradisional: **15 s/d 40 detik**.*

Pada fitur `/trx`, browser **sama sekali tidak dijalankan**. Skrip menggunakan library HTTP Python (`requests`) untuk langsung menembak API JSON backend Shopee secara native, sehingga waktu jaringan murni hanya memakan **200 s/d 800 milidetik**.

### B. Mekanisme Detail Penyuntikan Token & Cookies (Virtual Switch)

Pada arsitektur Shopee Partner Portal (`partner.shopee.co.id`), satu akun master (`allvbadmin`) memiliki hak akses atas puluhan merchant/outlet sekaligus. Shopee tidak mengharuskan login ulang untuk berpindah toko; hak akses dan konteks merchant sepenuhnya dikontrol melalui **kombinasi token autentikasi dan cookie konteks toko**.

#### 1. Anatomi Token & Cookies yang Disuntikkan

| Parameter Cookie | Asal / Sumber | Peran Teknis & Karakteristik |
| :--- | :--- | :--- |
| `shopee_tob_token` | [`agency/data/session.json`](file:///root/home/akbar/weekly/agency/data/session.json) | **Master Auth Token (To-Business)**. Kunci enkripsi sesi login akun master. Berfungsi sebagai bukti autentikasi utama ke backend Shopee. |
| `shopee_foody_mid` | Disuntik dinamis dari MID / SID cache | **Context Switcher (Kunci Utama)**. Nilai ID merchant target (contoh: `"1146482"`). Mengarahkan server Shopee agar mengeksekusi request dalam konteks outlet yang dipilih. |
| `shopee_tob_entity_id` | Dipaksa kosong (`""`) | **Entity Neutralizer**. Wajib disetel string kosong (`""`). Jika terisi entity ID default login, server Shopee akan mengunci request ke entitas default dan menolak query data pesanan dari merchant lain (Authorization/Scope Mismatch). |
| `__shopee_partner_website_x_token_live` | [`agency/data/session.json`](file:///root/home/akbar/weekly/agency/data/session.json) | **JWT Partner Web Session**. Token pendukung berisi payload terenkripsi klaim user ID master dan business region (`ID`). |
| `_sapid` & `shopee_request_from` | [`agency/data/session.json`](file:///root/home/akbar/weekly/agency/data/session.json) | **Fingerprint & Origin Identity**. Memastikan request dikenali valid sebagai panggilan dari `partner_web`. |

---

#### 2. Alur Teknis Penyuntikan (Code Flow di Python)

Proses injeksi cookie dilakukan di fungsi [`fetch_order_api()`](file:///root/home/akbar/weekly/agency/shopee/fetch_single_order.py#L115-L177):

```python
# 1. Ekstraksi token dari session.json
with open(session_file, "r", encoding="utf-8") as f:
    sess = json.load(f)

tob_token = sess.get("shopee_tob_token")
cookies = dict(sess.get("extra_cookies", {}))
cookies["shopee_tob_token"] = tob_token

# 2. Iterasi kandidat Merchant ID (MID) atau Store ID (SID) dari cache
for cid in all_to_try:
    # 3. PENYUNTIKAN DINAMIS:
    cookies["shopee_foody_mid"] = str(cid)      # Setel ID merchant target
    cookies["shopee_tob_entity_id"] = ""        # Netralkan entity ID

    # 4. Rekonstruksi Header HTTP Cookie standar
    headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

    # 5. Direct GET Request ke Shopee Seller API
    resp = requests.get(url, headers=headers, timeout=15)
```

#### 3. Mengapa Teknik Penyuntikan Ini Efektif?
- **Zero Overhead Re-login:** Tidak perlu memanggil endpoint `/login` Shopee berulang kali.
- **Atomic Context Switch:** Mengganti target merchant cukup dengan mengubah string `shopee_foody_mid` dalam millidetik tanpa perlu network handshake baru.
- **Multi-ID Candidate Traversal:** Jika pencarian pesanan menggunakan MID utama gagal, skrip otomatis mencoba Store ID (SID) turunan pada loop yang sama menggunakan session token yang tetap aktif.

---

### C. Fallback Cerdas (Self-Healing)
Jika token sesi di `session.json` telah kedaluwarsa (*token invalid* / code `1130001`):
Skrip secara otomatis beralih ke fallback browser (`get_session()`) untuk menyegarkan sesi dan mengambil token baru, lalu menyimpannya kembali ke `session.json` untuk request berikutnya.

---

## 5. Rincian Endpoint, Header, & Validasi Shopee API

### Request Spesifikasi Lengkap
```http
GET /api/seller/web/orders/3286071779363840692?feature_flag=64 HTTP/1.1
Host: foody.shopee.co.id
Accept: application/json, text/plain, */*
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36
X-Sf-Platform: 2
Operate-Source: partnerapp
Origin: https://partner.shopee.co.id
Referer: https://partner.shopee.co.id/
Cookie: shopee_tob_token=B:EEBJN4...; shopee_foody_mid=1146482; shopee_tob_entity_id=; _sapid=1f660...; shopee_request_from=partner_web; __shopee_partner_website_x_token_live=eyJhbGciOi...
```

### Parameter & Header Kritis:
- **`Cookie` (Injected):** Memuat autentikasi akun master dan identitas MID target yang sudah disuntikkan secara dinamis.
- **`X-Sf-Platform: 2` & `Operate-Source: partnerapp`:** Header identitas aplikasi mitra internal Shopee; memvalidasi bahwa pemanggil adalah sistem resmi partner web.
- **`Origin` & `Referer`:** Wajib merujuk ke domain `https://partner.shopee.co.id/` untuk melewati proteksi CSRF/CORS internal gateway Shopee.
- **`feature_flag=64`:** Parameter resmi dari Shopee Partner Portal untuk menyertakan seluruh rincian harga terpisah (*money scale / settlement breakdown*), status pembatalan, snapshot menu, modifier item, dan koordinat delivery.

### Response JSON (Ringkasan Struktur)
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "order": {
      "id": "3286071779363840692",
      "buyer_id": "1179573528",
      "status": 440,
      "create_time": 1790967349940,
      "store": {
        "id": 1148112,
        "min_spend": 0
      },
      "delivery_address": {
        "name": "zee",
        "phone": "*",
        "location": {}
      },
      "items": [
        {
          "id": "3286071781706240",
          "cart_item": {
            "detail": {
              "dish": {
                "name": "Nasi Ayam Katsu Sambal Ijo",
                "price": "2939000000"
              }
            },
            "quantity": 1
          },
          "merchant_subtotal": "2939000000"
        }
      ],
      "amount": {
        "total_amount": "5630000000"
      }
    }
  }
}
```

---

## 6. Format Input & Penanganan Timeout

1. **Pemilihan Merchant:**
   - Dropdown memuat seluruh 71 merchant yang terdaftar di Google Sheets (baik berstatus `Live` maupun `Pending`).
   - Tidak ada prefix portal angka yang mengganggu, murni nama merchant yang sesuai di Shopee Partner.

2. **Input Tanggal:**
   - Format: `DD-MM-YYYY` (contoh: `21-09-2026`).
   - Bot otomatis mengonversi ke format folder server: `2026-09-21_to_2026-09-27`.

3. **Batas Timeout:**
   - Timeout interaksi dropdown dan modal diatur ke **15 Menit** (`900.000 ms`), batas maksimal interaction token Discord, sehingga pengguna memiliki waktu yang leluasa untuk mencari Order ID tanpa terputus.

---

## 7. Pemeliharaan & Operasional

### Menjalankan CLI Manual
Anda dapat menguji penarikan langsung dari terminal server:
```bash
cd /root/home/akbar/weekly
agency/.venv/bin/python agency/shopee/fetch_single_order.py \
  --merchant "NASI Grg DAN BAKMIE ROSE_" \
  --order-id "3286071779363840692" \
  --date-range "2026-09-21_to_2026-09-27"
```

### Restart Service Bot
Jika melakukan perubahan kode pada bot Discord:
```bash
systemctl restart weekly-discord-bot.service
```

### Memantau Log Interaksi Bot
```bash
journalctl -u weekly-discord-bot.service -n 50 -f
```
