ALTER TABLE outlet_states ADD COLUMN IF NOT EXISTS timezone varchar(64) NOT NULL DEFAULT 'Asia/Jakarta';

UPDATE outlet_states
   SET timezone='Asia/Jakarta'
 WHERE timezone IS NULL OR BTRIM(timezone)='';

INSERT INTO schema_migrations (version) VALUES ('012_outlet_timezone')
ON CONFLICT (version) DO NOTHING;
