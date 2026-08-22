-- Ownership type is no longer a domain discriminator.
-- Regular/VB separation is represented by vb_brand_outlets membership.

ALTER TABLE outlets DROP COLUMN IF EXISTS ownership_type;

INSERT INTO schema_migrations (version) VALUES ('005_remove_ownership_type') ON CONFLICT (version) DO NOTHING;
