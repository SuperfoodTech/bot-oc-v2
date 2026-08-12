-- 002_separate_merchant_outlet.sql
-- Optimizing indices and hierarchy relations for Merchant (Mitra & Portal) -> Outlet separation.

CREATE INDEX IF NOT EXISTS idx_merchants_name ON merchants (name);
CREATE INDEX IF NOT EXISTS idx_portals_merchant_id ON portals (merchant_id);
CREATE INDEX IF NOT EXISTS idx_outlets_merchant_portal ON outlets (merchant_id, portal_id);
CREATE INDEX IF NOT EXISTS idx_outlets_store_id ON outlets (store_id);

-- Register migration
INSERT INTO schema_migrations (version) VALUES ('002_separate_merchant_outlet') ON CONFLICT (version) DO NOTHING;
