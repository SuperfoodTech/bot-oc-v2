ALTER TABLE outlet_states ADD COLUMN IF NOT EXISTS pause_mode varchar(20);

UPDATE outlet_states
   SET pause_mode='LEGACY'
 WHERE pause_until IS NOT NULL
   AND pause_mode IS NULL;

INSERT INTO schema_migrations (version) VALUES ('011_pause_mode')
ON CONFLICT (version) DO NOTHING;
