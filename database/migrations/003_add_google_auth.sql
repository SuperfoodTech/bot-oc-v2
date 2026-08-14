-- 003_add_google_auth.sql
-- Add google_email field to dashboard_accounts for Google OAuth 2.0 integration.

ALTER TABLE dashboard_accounts ADD COLUMN IF NOT EXISTS google_email varchar(255) UNIQUE;

-- Register migration
INSERT INTO schema_migrations (version) VALUES ('003_add_google_auth') ON CONFLICT (version) DO NOTHING;
