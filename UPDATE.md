# Update

## Virtual Brand Bot

- Added the `main-vb` patrol service with brand-level controls and merchant switching.
- Added VB database migrations for brand mappings, removal of `ownership_type`, compact bot observability, and outlet-level error tracing.
- Added the Virtual Brand admin tab with brand cards, merchant/outlet details, and brand-level ON/PAUSED control.
- Unified the Logs tab for Bot O/C and Virtual Brand with compact summaries, recent changes, and traceable Store ID errors.
- Updated the regular spreadsheet importer for the current 11-column layout after removal of the ownership column.
- Configured VB to use `main-vb/src/data/session.json`, `main-vb/src/data/credentials.json`, and the `shopee_profile` Chrome subprofile.
- VB browser runs with `HEADLESS=false` when started with the documented command.

## Validation

- Python compilation passed for `src` and `main-vb/src`.
- Admin dashboard JavaScript syntax validation passed.
- PostgreSQL migrations through `006_log_overview_and_errors` applied successfully.
- Regular spreadsheet fetch and VB import were validated against the configured sources.
