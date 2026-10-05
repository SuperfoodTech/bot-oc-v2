-- Migration 016: Add pause_from and requested_pause_from for Scheduled Pause
ALTER TABLE outlet_states ADD COLUMN IF NOT EXISTS pause_from timestamptz;
ALTER TABLE vb_brands ADD COLUMN IF NOT EXISTS pause_from timestamptz;
ALTER TABLE vb_brands ADD COLUMN IF NOT EXISTS requested_pause_from timestamptz;
