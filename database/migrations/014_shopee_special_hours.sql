-- Store the latest read-only special hours schedule fetched from Shopee Partner XHR.
ALTER TABLE outlet_states ADD COLUMN IF NOT EXISTS shopee_special_hours jsonb;
INSERT INTO schema_migrations (version) VALUES ('014_shopee_special_hours') ON CONFLICT (version) DO NOTHING;
