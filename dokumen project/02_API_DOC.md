# Dokumentasi API FoodMaster Bot O/C

## 1. Gambaran umum

Repo ini mengekspos tiga lapisan API:

| Layanan | Base URL lokal | Fungsi |
|---|---|---|
| Monolith utama | `http://localhost:3001` | UI admin, UI mitra, REST API, SSE |
| Bot control API | internal daemon `main-bot`, port `8081` | Health, status, pause/start, instant sync |
| Legacy VB API | opsional, port `8082` | API lama VB; default dinonaktifkan |

FastAPI docs default tersedia saat service utama hidup:

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

## 2. Autentikasi

### 2.1 Admin

- Login: `POST /api/v1/admin/login`
- Hasil: signed cookie `foodmaster_admin_session`
- TTL session: 12 jam
- Dipakai oleh hampir semua endpoint admin

### 2.2 Mitra

- Login: `POST /api/v1/user/login`
- Hasil: signed cookie `foodmaster_user_session`
- TTL session: 12 jam
- Cookie ini terutama dipakai untuk SSE `GET /api/v1/user/events`

### 2.3 Google Auth

- Flow tersedia di:
  - `GET /api/v1/auth/google/login`
  - `GET /api/v1/auth/google/callback`
- Hanya aktif bila `GOOGLE_AUTH_ENABLED=true` dan credential OAuth tersedia.

## 3. Objek runtime utama

### 3.1 Store status object

Endpoint seperti `GET /api/v1/stores`, `GET /api/v1/stores/{store_id}`, `GET /api/v1/admin/users`, dan `POST /api/v1/user/login` mengembalikan outlet dengan field inti berikut:

| Kelompok | Field utama |
|---|---|
| Identitas | `store_id`, `store_name`, `merchant_name`, `nama_portal`, `nama_pemilik` |
| Akun / paket | `account_username`, `paket`, `tanggal_mulai_layanan`, `tanggal_berakhir_layanan`, `vercel_link`, `vercel_password`, `google_email` |
| Control state | `vercel_status`, `pause_until`, `pause_mode`, `subscription_status`, `is_suspended`, `alasan_penangguhan` |
| Live state | `shopee_status`, `live_state`, `desired_state`, `within_operating_schedule`, `timezone` |
| Schedule | `shopee_regular_hours`, `schedule_available`, `schedule_fetch_status`, `schedule_fetch_attempted_at`, `schedule_fetch_succeeded_at`, `schedule_fetch_error` |
| UI state | `bot_phase`, `display_toggle_on`, `display_toggle_disabled`, `display_toggle_reason`, `display_status_bucket`, `display_status_label`, `display_status_tone`, `display_note` |
| Audit ringkas | `last_synced_at`, `last_action`, `last_toggle_action_raw`, `last_toggle_reason`, `last_toggle_at` |

### 3.2 Enum penting

| Field | Nilai |
|---|---|
| `vercel_status` | `ON`, `OFF` |
| `shopee_status` | `ON`, `PAUSE`, `CLOSED`, `UNKNOWN` |
| `schedule_fetch_status` | `NOT_FETCHED_YET`, `FETCH_RETRYING`, `FETCHED_EMPTY`, `READY` |
| `pause_mode` | `REST_OF_DAY`, `FIXED_DURATION`, `CUSTOM`, `LEGACY`, `null` |

## 4. HTML routes

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/` | Tidak | Redirect ke `/admin/dashboard` |
| `GET` | `/admin` | Tidak | Redirect ke `/admin/dashboard` |
| `GET` | `/admin/dashboard` | Cookie admin | Halaman utama admin |
| `GET` | `/admin/login` | Tidak | Halaman login admin |
| `GET` | `/admin/bot` | Tidak | Redirect ke tab logs |
| `GET` | `/admin/logs` | Tidak | Redirect ke tab logs |
| `GET` | `/admin/mitra/tambah` | Cookie admin | Saat ini selalu `403` |
| `GET` | `/app` | Tidak | Halaman dashboard mitra |
| `GET` | `/mitra/{slug}` | Tidak | Halaman dashboard mitra dengan slug |

## 5. Admin auth dan account

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `POST` | `/api/v1/admin/login` | Tidak | Login admin dan set cookie |
| `POST` | `/api/v1/admin/logout` | Cookie admin | Hapus cookie admin |
| `GET` | `/api/v1/admin/me` | Cookie admin | Profil admin yang sedang login |
| `GET` | `/api/v1/admin/accounts` | Cookie admin | List akun admin |
| `PATCH` | `/api/v1/admin/account` | Cookie admin | Ubah username/password admin sendiri |
| `POST` | `/api/v1/admin/accounts` | Cookie admin | Buat akun admin baru |
| `GET` | `/api/v1/auth/google/login` | Tidak | Redirect OAuth Google |
| `GET` | `/api/v1/auth/google/callback` | Tidak | Callback OAuth Google |

### 5.1 Request body penting

`POST /api/v1/admin/login`

```json
{
  "username": "admin",
  "password": "Admin@123"
}
```

`PATCH /api/v1/admin/account`

```json
{
  "username": "admin-baru",
  "password": "opsional",
  "google_email": "opsional@example.com"
}
```

`POST /api/v1/admin/accounts`

```json
{
  "username": "ops-admin",
  "password": "rahasia",
  "google_email": "opsional@example.com"
}
```

## 6. Admin data Agency dan Virtual Brand

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/api/v1/admin/users` | Cookie admin | List owner/mitra beserta outlet dari PostgreSQL |
| `POST` | `/api/v1/admin/sync-source` | Cookie admin | Import Agency dari Google Sheet ke PostgreSQL |
| `GET` | `/api/v1/admin/vb/brands` | Cookie admin | List brand VB |
| `GET` | `/api/v1/admin/vb/brands/{brand_id}` | Cookie admin | Detail brand VB beserta outlet |
| `PATCH` | `/api/v1/admin/vb/brands/{brand_id}/status` | Cookie admin | Simpan `requested_status` brand VB |
| `POST` | `/api/v1/admin/vb/import` | Cookie admin | Import matrix VB dari Google Sheet |
| `POST` | `/api/v1/admin/generate-link` | Cookie admin | Generate / rotate link dan passcode mitra |
| `DELETE` | `/api/v1/admin/outlets/{store_id}` | Cookie admin | Hapus outlet, dengan write-back ke Apps Script lebih dulu |
| `DELETE` | `/api/v1/admin/users/{nama_pemilik}` | Cookie admin | Hapus merchant / partner dan semua outlet terkait |

### 6.1 Request body penting

`PATCH /api/v1/admin/vb/brands/{brand_id}/status`

```json
{
  "status": "PAUSED",
  "duration_type": "30_min",
  "custom_minutes": null,
  "custom_until": null
}
```

`POST /api/v1/admin/generate-link`

```json
{
  "nama_pemilik": "Mitra Budi",
  "passcode": "Budi@123"
}
```

### 6.2 Respons penting

`GET /api/v1/admin/users`

```json
{
  "success": true,
  "users": [
    {
      "nama_pemilik": "Mitra A",
      "nama_portal": "WonderFood",
      "total_outlets": 2,
      "outlets": [
        {
          "store_id": "21897166",
          "store_name": "Outlet A",
          "vercel_status": "ON",
          "shopee_status": "CLOSED"
        }
      ]
    }
  ]
}
```

`PATCH /api/v1/admin/vb/brands/{brand_id}/status`

```json
{
  "success": true,
  "brand": {
    "id": "uuid",
    "name": "Katsunami",
    "applied_status": "ON",
    "requested_status": "PAUSED"
  },
  "message": "Perubahan disimpan dan menunggu giliran brand berikutnya."
}
```

## 7. Endpoint admin yang masih ada tetapi saat ini dinonaktifkan

| Method | Path | Status aktual | Catatan |
|---|---|---|---|
| `POST` | `/api/v1/admin/outlets` | `403` | Tambah mitra/outlet wajib lewat Google Sheet lalu fetch |
| `POST` | `/api/v1/admin/suspend` | `403` | Pengaturan suspend via dashboard dimatikan |
| `POST` | `/api/v1/admin/renew` | `403` | Renew subscription via dashboard dimatikan |
| `POST` | `/api/v1/admin/outlets/edit` | `403` | Edit outlet via dashboard dimatikan |

UI untuk endpoint-endpoint ini masih ada, tetapi backend aktif sudah menolaknya.

## 8. Endpoint mitra / user dashboard

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `POST` | `/api/v1/user/login` | Tidak | Login mitra pakai passcode, set cookie user, dan kirim daftar outlet |
| `GET` | `/api/v1/user/outlets` | Query param | Ambil outlet milik `nama_pemilik` |
| `POST` | `/api/v1/user/pause` | Tidak wajib cookie; admin cookie memberi hak istimewa | Simpan permintaan tutup sementara |
| `POST` | `/api/v1/user/resume` | Query param `store_id` | Simpan permintaan buka kembali |
| `GET` | `/api/v1/user/history` | Query param `store_ids` | Ambil log terbaru untuk store tertentu |
| `GET` | `/api/v1/user/events` | Cookie user | SSE perubahan status outlet untuk owner yang login |

### 8.1 Request body penting

`POST /api/v1/user/login`

```json
{
  "passcode": "Budi@123",
  "slug": "opsional-slug"
}
```

`POST /api/v1/user/pause`

```json
{
  "store_id": "21897166",
  "duration_type": "rest_of_day",
  "custom_until": null,
  "custom_minutes": null
}
```

`POST /api/v1/user/resume`

Tidak memakai body. Parameter dikirim lewat query:

```text
/api/v1/user/resume?store_id=21897166
```

### 8.2 Catatan perilaku

1. `POST /api/v1/user/pause` akan menolak outlet yang sedang `SUSPENDED` jika caller bukan admin.
2. Mitra juga akan ditolak bila toggle terkunci karena:
   - menunggu fetch jadwal,
   - fetch jadwal gagal,
   - jadwal Shopee kosong,
   - di luar jadwal operasional.
3. Saat dipanggil dari dashboard admin, endpoint pause yang sama boleh dipakai untuk menutup outlet tanpa gate milik mitra.

## 9. Shared store, toggle, log, dan monitoring endpoint

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/api/v1/health` | Tidak | Health service monolith |
| `GET` | `/api/v1/stores` | Cookie admin | Flat list store runtime |
| `GET` | `/api/v1/stores/{store_id}` | Cookie admin | Detail satu store |
| `POST` | `/api/v1/toggle` | Cookie admin | Ubah toggle outlet reguler dari dashboard admin |
| `POST` | `/api/v1/sync` | Cookie admin | Compatibility endpoint; hanya mengembalikan snapshot runtime |
| `GET` | `/api/v1/logs` | Cookie admin | Audit log outlet reguler |
| `GET` | `/api/v1/admin/logs/overview` | Cookie admin | Ringkasan log reguler dan VB |
| `GET` | `/api/v1/admin/events` | Cookie admin | SSE semua perubahan state outlet |
| `GET` | `/api/v1/admin/bot-status` | Cookie admin | Status daemon bot reguler |
| `GET` | `/api/v1/admin/bot/activity` | Cookie admin | Ringkasan cycle bot terakhir |
| `POST` | `/api/v1/admin/bot/control` | Cookie admin | Start, pause, atau sync bot reguler |

### 9.1 Request body penting

`POST /api/v1/toggle`

```json
{
  "store_id": "21897166",
  "status": "OFF",
  "pause_duration_minutes": null,
  "duration_type": "30_min",
  "custom_until": null
}
```

`POST /api/v1/admin/bot/control`

```json
{
  "action": "pause"
}
```

### 9.2 Respons penting

`GET /api/v1/admin/bot-status`

```json
{
  "is_online": true,
  "status_text": "Online",
  "status_class": "badge-open",
  "detail_text": "Patroli aktif (Siklus #12)"
}
```

`GET /api/v1/admin/logs/overview`

```json
{
  "summary": {
    "REGULAR": { "event_count": 10, "last_event_at": "2026-09-01 08:00:00" },
    "VB": { "event_count": 4, "last_event_at": "2026-09-01 07:58:00" }
  },
  "recent": [],
  "errors": []
}
```

## 10. Bot control API internal (`main-bot`, port 8081)

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/health` | Tidak | Health bot API |
| `GET` | `/bot/status` | Tidak | Trace status bot |
| `GET` | `/bot/activity` | Tidak | Aktivitas cycle bot |
| `POST` | `/bot/start` | Tidak | Ubah status bot jadi `running` |
| `POST` | `/bot/pause` | Tidak | Ubah status bot jadi `paused` |
| `POST` | `/bot/sync` | Tidak | Trigger sync instan, opsional `execute_actions` |
| `GET` | `/bot/logs` | Tidak | Ambil log terbaru dari DB |

Catatan:

- API ini dipakai daemon dan backend admin.
- Status pause/running dipersist ke `main-bot/src/bot_state.json`.

## 11. Legacy VB API (`main-vb/src/api.py`, opsional port 8082)

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/health` | Tidak | Health check |
| `GET` | `/api/vb/brands` | Header `x-admin-token` | Default `410` bila legacy API tidak diaktifkan |
| `PATCH` | `/api/vb/brands/{brand_id}/status` | Header `x-admin-token` | Default `410` bila legacy API tidak diaktifkan |

Gunakan endpoint `/api/v1/admin/vb/*` pada monolith utama sebagai jalur kontrol resmi.

## 12. Known caveats dari implementasi saat ini

1. `GET /api/v1/user/outlets` dan `GET /api/v1/user/history` mengandalkan query param, bukan guard cookie user. Ini adalah perilaku implementasi saat ini.
2. `POST /api/v1/sync` tidak menjalankan bot; ia hanya mengembalikan state DB.
3. Beberapa flow admin masih terlihat di UI, tetapi ditolak backend dengan `403`.
4. Password disimpan plaintext di DB sehingga integrasi API internal harus dianggap sensitif.
