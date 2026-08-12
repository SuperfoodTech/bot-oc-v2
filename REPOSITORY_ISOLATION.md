# Struktur Repository & Arsitektur Monolith FoodMaster

Repository **bot-oc** menggunakan **FastAPI Monolith Architecture** yang menyatukan Web Dashboard (Admin Console & Mitra User Link) dan Backend API dalam satu service, serta **Shopee Automation Bot Engine** sebagai service independen.

---

## Peta Komponen Repository

| Folder / File | Fungsi & Peran | Host / Port |
|---|---|---|
| `src/backend/` | Monolith FastAPI Engine (API Admin/User, Health Check, Auth Session, Static Assets & HTML Templates) | `http://localhost:3001` |
| `src/core/` | Core Modules (Decision Engine, Sheet Parser, Custom Logger) | Shared Library |
| `main-bot/` | Shopee Auto Open/Close Selenium Daemon Service | Bot API `8081` |
| `database/` | Skema Migration PostgreSQL (`001_initial_schema.sql`) | PostgreSQL `5435` |
| `scripts/` | Shell launcher (`dev.sh`, `prod.sh`) & Spreadsheet Master Importer (`import_sheet.py`) | CLI |
| `tests/` | Automated Test Suite (`test_frontend_routes.py`, `test_backend_api.py`, `test_full_backend_api.py`) | Test Client |

---

## Aturan Struktur & Modul

1. **Monolith FastAPI**:
   - Seluruh route UI (Admin Console `/admin`, Login `/admin/login`, Mitra Dashboard `/mitra/{link_slug}` & `/app`) disajikan langsung dari `src/backend/main.py`.
   - Asset static berada di `src/backend/static/` dan template HTML di `src/backend/templates/`.
   - Folder `web/` legacy yang sebelumnya memisahkan frontend sudah dibersihkan/dihapus.

2. **Source of Truth Runtime**:
   - Database PostgreSQL adalah *source of truth* tunggal operasional aplikasi.
   - Google Spreadsheet hanya di-import satu kali via `scripts/import_sheet.py` atau tombol Sync di Admin Console.

3. **Bot Service (`main-bot/`)**:
   - Bot berjalan 24/7 membaca database PostgreSQL.
   - Menggunakan 1 browser persistent session dengan akun Shopee `auto7313`.

4. **Aturan Update Non-Bot (Zero-Downtime)**:
   - Untuk setiap update frontend/backend web (`src/backend/`, HTML, CSS, REST API), **wajib** menggunakan:
     `docker compose build web && docker compose up -d --no-deps web`
   - Dilarang menggunakan `docker compose down` / `prod.sh` jika tidak ada perubahan pada core bot atau skema database, agar `fm-bot` tetap aktif tanpa terputus.

---

## Menjalankan Service

### 1. Development Lokal (FastAPI Monolith)
```bash
./scripts/dev.sh
```
Akses Dashboard Admin & User: `http://localhost:3001`

### 2. Full Stack Docker Compose (PostgreSQL, Monolith, & Bot Service)
```bash
docker compose up -d --build
```

---

## Menjalankan Automated Tests

Seluruh pengujian integrasi & unit test dapat dijalankan dari folder `tests/`:
```bash
PYTHONPATH=src uv run python tests/test_frontend_routes.py
PYTHONPATH=src uv run python tests/test_backend_api.py
PYTHONPATH=src uv run python tests/test_full_backend_api.py
```
