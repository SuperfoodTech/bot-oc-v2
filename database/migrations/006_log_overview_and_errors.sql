-- Compact bot observability: summaries are snapshots, details are errors/changes only.
CREATE TABLE IF NOT EXISTS vb_brand_runtime_status (
    vb_brand_id uuid PRIMARY KEY REFERENCES vb_brands(id) ON DELETE CASCADE,
    last_patrol_run_id bigint REFERENCES vb_patrol_runs(id),
    last_patrolled_at timestamptz,
    outlets_processed integer NOT NULL DEFAULT 0,
    outlets_changed integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    last_error_at timestamptz,
    last_error_message text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_errors (
    id bigserial PRIMARY KEY,
    mode varchar(20) NOT NULL CHECK (mode IN ('REGULAR', 'VB')),
    patrol_run_id bigint REFERENCES vb_patrol_runs(id) ON DELETE SET NULL,
    vb_brand_id uuid REFERENCES vb_brands(id) ON DELETE SET NULL,
    outlet_id uuid REFERENCES outlets(id) ON DELETE SET NULL,
    store_id varchar(100) NOT NULL,
    merchant_name varchar(255),
    action varchar(40) NOT NULL,
    attempt_count integer NOT NULL DEFAULT 1,
    error_type varchar(100),
    error_message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS automation_errors_created_idx ON automation_errors (created_at DESC);
CREATE INDEX IF NOT EXISTS automation_errors_mode_created_idx ON automation_errors (mode, created_at DESC);
CREATE INDEX IF NOT EXISTS automation_errors_store_created_idx ON automation_errors (store_id, created_at DESC);

INSERT INTO schema_migrations (version) VALUES ('006_log_overview_and_errors') ON CONFLICT (version) DO NOTHING;
