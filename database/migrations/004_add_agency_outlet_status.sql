-- 004_add_agency_outlet_status.sql
-- Menyimpan hasil inspeksi status aktual outlet churn dari ShopeeFood.
-- Data ini diperbarui oleh agency patrol bot setiap cycle.

CREATE TABLE IF NOT EXISTS agency_outlet_status (
    store_id        TEXT PRIMARY KEY,
    merchant_name   TEXT NOT NULL DEFAULT '',
    brand           TEXT NOT NULL DEFAULT '',
    shopee_status   TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_checked    TIMESTAMPTZ,
    last_action     TEXT NOT NULL DEFAULT ''
);
