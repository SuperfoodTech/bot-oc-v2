-- Store the latest read-only schedule fetched from Shopee Partner XHR.
ALTER TABLE outlet_states ADD COLUMN IF NOT EXISTS shopee_regular_hours jsonb;
INSERT INTO schema_migrations (version) VALUES ('007_shopee_regular_hours') ON CONFLICT (version) DO NOTHING;
