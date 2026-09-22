-- Migration 015: Add owner_name and owner_slug to vb_brands
ALTER TABLE vb_brands
  ADD COLUMN IF NOT EXISTS owner_name VARCHAR(255),
  ADD COLUMN IF NOT EXISTS owner_slug VARCHAR(255);
