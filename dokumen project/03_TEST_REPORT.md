# Test Report FoodMaster Bot O/C

## 1. Ringkasan eksekusi

- Waktu eksekusi: `2026-09-01 08:27:41 WIB`
- Environment Python: `Python 3.12.12`
- Root repo: `/home/akbarhann/project/bot-oc`
- Runner utama: `uv run pytest`

## 2. Command yang dijalankan

### 2.1 Koleksi test

```bash
uv run pytest --collect-only -q
```

Hasil: `54 tests collected`

### 2.2 Eksekusi test suite aktif

```bash
uv run pytest -q
```

Hasil aktual:

```text
54 passed, 1 warning in 1.68s
```

## 3. Hasil per file

| File | Jumlah test | Fokus |
|---|---:|---|
| `tests/test_backend_api.py` | 1 | Smoke test endpoint backend utama |
| `tests/test_daemon_schedule_fetch_contract.py` | 2 | Kontrak worker/daemon: fetch jadwal sebelum decision |
| `tests/test_dashboard_label_contract.py` | 3 | Konsistensi label status admin dan mitra |
| `tests/test_frontend_routes.py` | 1 | Render route HTML dan static asset |
| `tests/test_merchant_scheduler.py` | 4 | Scheduler per merchant / portal |
| `tests/test_multi_schedule_pause_logic.py` | 9 | Multi-interval schedule, pause boundary, weekday mapping Shopee |
| `tests/test_outlet_state_contract.py` | 11 | Derivasi state runtime untuk UI |
| `tests/test_pause_utils.py` | 3 | Resolusi pause `rest_of_day` |
| `tests/test_regular_hours_store_identity.py` | 4 | Guard mismatch `store_id` saat fetch Shopee |
| `tests/test_schedule_ui_layout_contract.py` | 11 | Contract markup/CSS dashboard admin, mitra, dan VB |
| `tests/test_timezone_support.py` | 5 | WIB/WITA/WIT dan evaluasi timezone outlet |
| **Total** | **54** | **Semua lulus** |

## 4. Area yang tervalidasi dengan baik

### 4.1 Decision dan scheduling logic

Suite aktif cukup kuat untuk area berikut:

- prioritas open/close terhadap mismatch live state,
- pause yang melewati break antar sesi,
- penentuan recheck tercepat,
- grouping scheduler per merchant/portal,
- mapping weekday API Shopee `1=Sunday` sampai `7=Saturday`,
- fallback timezone outlet ke WIB bila input tidak dikenal.

### 4.2 Runtime state untuk dashboard

Tervalidasi:

- perbedaan `desired_state`, `live_state`, dan `bot_phase`,
- label UI seperti `Menunggu fetch jadwal`, `Jadwal Shopee belum diatur`, `Sedang Tutup - Di luar jadwal`, `Tutup Sementara`,
- toggle disabled state di admin dan mitra,
- konsistensi tampilan schedule dan log layout di template/CSS.

### 4.3 Guardrail integrasi Shopee

Tervalidasi:

- response regular-hours dengan `store_id` salah harus ditolak,
- response live state untuk store lain tidak dipakai,
- worker wajib fetch jadwal terlebih dahulu sebelum menjalankan decision.

## 5. Warning yang muncul

Selama `pytest`, ada 1 warning:

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.
```

Dampak:

- tidak membuat test gagal,
- tetapi ada technical debt pada stack `TestClient` yang sebaiknya dijadwalkan untuk dibersihkan.

## 6. Temuan penting dari pembacaan suite

1. Suite utama yang benar-benar aktif ada di folder `tests/` dan diatur oleh `pyproject.toml` (`testpaths = ["tests"]`).
2. Beberapa file bernama test ternyata bukan bagian dari suite aktif karena fungsi utamanya tidak memakai prefix `test_` atau dijalankan manual.
3. Test aktif lebih dominan berupa unit/contract test dan smoke test `FastAPI TestClient`, bukan E2E live browser.

## 7. Skrip test yang ditemukan tetapi tidak tercollect otomatis

| File | Status | Catatan |
|---|---|---|
| `tests/test_full_backend_api.py` | Manual | Fungsi utama `run_full_backend_tests()`, tidak dipanggil pytest |
| `main-bot/src/test_full_system_communication.py` | Manual | Smoke/integration script untuk backend + bot API |
| `main-bot/src/test_bot_chrome_profile_login.py` | Manual | Validasi login browser/profile Shopee |
| `main-bot/src/test_shopee_pull_and_open_pause.py` | Manual | Aksi live Shopee |
| `scripts/test_business_hours_flow.py` | Manual | Flow browser live ke Shopee Business Hours |

Catatan tambahan:

- `uv run pytest main-bot/src/test_full_system_communication.py main-bot/src/test_bot_chrome_profile_login.py main-bot/src/test_shopee_pull_and_open_pause.py --collect-only -q` menghasilkan `no tests collected`.
- Artinya ketiga file tersebut saat ini lebih tepat dianggap smoke script daripada automated regression suite.

## 8. Area yang belum benar-benar tervalidasi oleh suite aktif

1. Live browser automation ke Shopee secara end-to-end.
2. Validasi credential/session Selenium pada environment server.
3. Import real Google Sheet via network dan write-back real Apps Script.
4. Flow hapus outlet yang menyentuh Apps Script lalu delete DB.
5. Flow Google OAuth admin dan mitra.
6. Perilaku endpoint admin yang saat ini disabled (`403`) sebagai bagian dari UX.
7. Migrasi database pada database kosong versus database production-like yang sudah berisi data besar.

## 9. Risiko residual

Walaupun suite aktif lulus 100%, ada beberapa risiko yang masih perlu dianggap terbuka:

1. Integrasi paling berisiko ada di browser automation dan jaringan Shopee, sementara area itu belum diuji otomatis pada run ini.
2. Sebagian smoke test lama di repo terlihat sudah out-of-date terhadap perilaku backend sekarang, jadi tidak bisa lagi dijadikan bukti coverage tanpa diperbarui.
3. Beberapa test API bergantung pada state lokal yang sudah cukup siap untuk import app dan login admin. Jadi hasil hijau ini lebih kuat untuk regression logic dibanding readiness deployment dari nol.

## 10. Kesimpulan

Status test saat ini baik untuk:

- decision engine,
- runtime state derivation,
- scheduler,
- kontrak tampilan admin/mitra/VB,
- smoke test route utama.

Status test saat ini belum cukup untuk menyatakan aman sepenuhnya pada:

- live Shopee automation,
- OAuth,
- real spreadsheet write-back,
- disaster recovery database.
