# Main VB

Service boundary untuk Virtual Brand. Folder `src/core` merupakan salinan awal dari `src/core` bot-oc.

## Runtime data binding

Binding lokal berikut sengaja berupa symlink agar credential, session, dan Chrome profile tidak diduplikasi:

| Path yang dipakai `main-vb` | Sumber lokal |
|---|---|
| `main-vb/src/data/credentials.json` | `/home/akbarhann/project/bot-oc/src/data/credentials allvbadmin.json` |
| `main-vb/src/data/session.json` | `/home/akbarhann/project/bot-oc/src/data/session.json` |
| `main-vb/src/data/chrome_profile` | `/home/akbarhann/project/bot-oc/src/data/chrome_profile` |

Jangan commit isi credential, session, atau Chrome profile. Binding ini bersifat environment-local dan perlu dibuat ulang pada environment lain.

`browser.py` pada salinan `main-vb` sekarang hanya menerima referensi default VB: `session.json`, `credentials.json`, `chrome_profile`, dan subprofile `shopee_profile`. Mekanisme login, recovery, token, OTP, serta merchant switch tidak diubah.

## Perlindungan browser core

`src/core/browser.py` bot-oc tetap identik dengan versi sebelumnya. `main-vb/src/core/browser.py` sengaja berbeda hanya pada referensi default path dan profile directory agar memakai credential/session/profile VB.

Environment variable `VB_SESSION_FILE`, `VB_CREDENTIALS_FILE`, `VB_CHROME_PROFILE_DIR`, dan `VB_CHROME_PROFILE_NAME` dapat mengganti default tersebut secara eksplisit.

## Frontend

`frontend/vb_tab.html` adalah shell presentasi untuk tab VB. Data dan aksi toggle belum dihubungkan ke API database.

## Menjalankan komponen

Migration database: jalankan `database/migrations/004_virtual_brand.sql` setelah migration existing.

Patrol:

```bash
PYTHONPATH=main-vb/src python main-vb/src/daemon.py
```

API admin:

```bash
VB_ADMIN_API_TOKEN='<secret>' PYTHONPATH=main-vb/src uvicorn api:app --app-dir main-vb/src --port 8082
```

API legacy `main-vb/src/api.py` hanya menyediakan health check secara default. Endpoint kontrolnya dinonaktifkan agar tidak ada jalur autentikasi kedua. Jalur kontrol resmi adalah endpoint `/api/v1/admin/vb/*` pada backend utama dengan cookie admin existing.
