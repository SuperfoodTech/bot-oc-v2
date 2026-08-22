-- Virtual Brand control model.
-- Brand state is persisted separately from outlet_states because one brand
-- controls outlets across multiple Shopee portals.

CREATE TABLE IF NOT EXISTS vb_brands (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(255) NOT NULL,
    name_normalized varchar(255) NOT NULL UNIQUE,
    applied_status varchar(10) NOT NULL DEFAULT 'ON' CHECK (applied_status IN ('ON', 'PAUSED')),
    requested_status varchar(10) CHECK (requested_status IN ('ON', 'PAUSED')),
    requested_at timestamptz,
    requested_by uuid REFERENCES dashboard_accounts(id),
    last_applied_at timestamptz,
    last_patrolled_at timestamptz,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vb_brand_outlets (
    vb_brand_id uuid NOT NULL REFERENCES vb_brands(id) ON DELETE CASCADE,
    outlet_id uuid NOT NULL UNIQUE REFERENCES outlets(id) ON DELETE CASCADE,
    source_column varchar(255),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (vb_brand_id, outlet_id)
);

CREATE TABLE IF NOT EXISTS vb_patrol_runs (
    id bigserial PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status varchar(24) NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'SYNCED', 'PARTIAL_FAILURE', 'FAILED')),
    brands_processed integer NOT NULL DEFAULT 0,
    outlets_processed integer NOT NULL DEFAULT 0,
    error_message text
);

ALTER TABLE automation_logs ADD COLUMN IF NOT EXISTS mode varchar(20) NOT NULL DEFAULT 'OUTLET';
ALTER TABLE automation_logs ADD COLUMN IF NOT EXISTS vb_brand_id uuid REFERENCES vb_brands(id);
ALTER TABLE automation_logs ADD COLUMN IF NOT EXISTS vb_patrol_run_id bigint REFERENCES vb_patrol_runs(id);
ALTER TABLE admin_audit_logs ADD COLUMN IF NOT EXISTS vb_brand_id uuid REFERENCES vb_brands(id);

CREATE INDEX IF NOT EXISTS vb_brands_patrol_idx ON vb_brands (is_active, name_normalized);
CREATE INDEX IF NOT EXISTS vb_brand_outlets_brand_idx ON vb_brand_outlets (vb_brand_id);
CREATE INDEX IF NOT EXISTS automation_logs_vb_brand_idx ON automation_logs (vb_brand_id, checked_at DESC);

INSERT INTO schema_migrations (version) VALUES ('004_virtual_brand') ON CONFLICT (version) DO NOTHING;
