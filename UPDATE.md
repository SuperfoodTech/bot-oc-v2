# Update

## Latest update: v0.3.5

- Memperbaiki penerusan durasi pause dashboard ke payload Shopee melalui
  `pause_end_time` Unix timestamp milidetik.
- Menambahkan countdown sisa pause menuju outlet kembali ON.
- Menyeragamkan timezone tampilan dan log ke WIB/GMT+7 tanpa fractional seconds
  atau microseconds.
- Memperbesar dan mempertebal teks status serta log agar lebih mudah dibaca.
- Detail lengkap tersedia di [update/0.3.5.md](update/0.3.5.md).

## Latest deployment handoff

- Docker service definition for `bot-vb` was added to `docker-compose.yml`.
- The service uses the shared `foodmaster-bot-runtime:dev` image and the existing
  dependency layer; no second dependency installation is required.
- Server runtime is explicitly `HEADLESS=true`.
- The change was committed and pushed to `origin/main` as `0c3d5e9`.
- Docker build/start has not been executed from this development workspace;
  deployment must be performed by the server AI agent using the instructions
  below.

## Virtual Brand Bot

- Added the `main-vb` patrol service with brand-level controls and merchant switching.
- Added VB database migrations for brand mappings, removal of `ownership_type`, compact bot observability, and outlet-level error tracing.
- Added the Virtual Brand admin tab with brand cards, merchant/outlet details, and brand-level ON/PAUSED control.
- Unified the Logs tab for Bot O/C and Virtual Brand with compact summaries, recent changes, and traceable Store ID errors.
- Updated the regular spreadsheet importer for the current 11-column layout after removal of the ownership column.
- Configured VB to use `main-vb/src/data/session.json`, `main-vb/src/data/credentials.json`, and the `shopee_profile` Chrome subprofile.
- VB browser uses `HEADLESS=true` in the server Docker service; local debugging may override this explicitly.

## Server deployment: Bot VB Docker service

Bot VB now has its own service, `fm-bot-vb`, while reusing the same image and
dependency environment as `fm-bot`. There is no separate VB dependency
installation and no public VB port.

The service is configured server-side with `HEADLESS=true` and uses:

- `/app/vb-data/chrome_profile` for the VB Chrome profile;
- `/app/vb-data/session.json` for the VB session;
- `/app/vb-data/credentials.json` for the VB credential file;
- Chrome subprofile `shopee_profile`;
- the existing `fm-postgres` database network.

The host `src/data` directory is mounted at `/app/vb-data`; this avoids relying
on the local symlinks under `main-vb/src/data` inside the container.

### AI agent deployment instructions

1. Ensure the host files exist and are not committed:
   `src/data/chrome_profile`, `src/data/session.json`, and
   `src/data/credentials allvbadmin.json`.
2. The compose service maps the host credential file to
   `/app/vb-data/credentials.json` as read-only; verify the source file exists.
3. Build and start only the VB service with:

   ```bash
   docker compose build bot-vb
   docker compose up -d bot-vb
   ```

4. Verify startup with:

   ```bash
   docker compose ps bot-vb
   docker compose logs --tail=100 -f bot-vb
   ```

5. Confirm the logs contain `headless=True`, the `/app/vb-data/chrome_profile`
   path, and `shopee_profile`. Confirm the first patrol reports a brand,
   merchant, Store ID, action, and result.

6. Stop or restart only this service when needed:

   ```bash
   docker compose stop bot-vb
   docker compose restart bot-vb
   ```

Do not add a second dependency install, do not expose a new port, and do not
mount the VB profile into `fm-bot`. The VB service performs real Shopee actions
according to the persisted brand states.

## Validation

- Python compilation passed for `src` and `main-vb/src`.
- Admin dashboard JavaScript syntax validation passed.
- PostgreSQL migrations through `006_log_overview_and_errors` applied successfully.
- Regular spreadsheet fetch and VB import were validated against the configured sources.
