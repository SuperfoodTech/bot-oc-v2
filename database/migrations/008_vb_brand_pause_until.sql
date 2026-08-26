-- Timed pause for Virtual Brand controls.
ALTER TABLE vb_brands ADD COLUMN IF NOT EXISTS pause_until timestamptz;
ALTER TABLE vb_brands ADD COLUMN IF NOT EXISTS requested_pause_until timestamptz;

INSERT INTO schema_migrations (version) VALUES ('008_vb_brand_pause_until')
ON CONFLICT (version) DO NOTHING;
