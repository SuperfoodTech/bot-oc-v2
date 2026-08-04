-- FoodMaster Auto Open / Auto Close
-- PostgreSQL initial schema.
-- This migration is independent from the current SQLite adapter.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version varchar(100) PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS merchants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(255) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id uuid NOT NULL REFERENCES merchants(id),
    name varchar(255) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT portals_merchant_name_unique UNIQUE (merchant_id, name)
);

CREATE TABLE IF NOT EXISTS shopee_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    portal_id uuid NOT NULL REFERENCES portals(id),
    merchant_id_external varchar(100) NOT NULL,
    username varchar(255) NOT NULL,
    phone varchar(50),
    password_encrypted text,
    session_file text,
    is_active boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT shopee_accounts_portal_username_unique UNIQUE (portal_id, username)
);

CREATE TABLE IF NOT EXISTS dashboard_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id uuid REFERENCES merchants(id),
    username varchar(255) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role varchar(20) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT dashboard_accounts_role_check CHECK (role IN ('ADMIN', 'MERCHANT')),
    CONSTRAINT dashboard_accounts_merchant_check CHECK (
        (role = 'ADMIN' AND merchant_id IS NULL) OR
        (role = 'MERCHANT' AND merchant_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS outlets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id uuid NOT NULL REFERENCES merchants(id),
    portal_id uuid NOT NULL REFERENCES portals(id),
    shopee_account_id uuid REFERENCES shopee_accounts(id),
    store_id varchar(100) NOT NULL UNIQUE,
    ownership_type varchar(100),
    long_name varchar(255) NOT NULL,
    short_name varchar(255),
    special_hours text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS operating_hours (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    outlet_id uuid NOT NULL REFERENCES outlets(id) ON DELETE CASCADE,
    weekday smallint NOT NULL,
    open_time time,
    close_time time,
    is_closed boolean NOT NULL DEFAULT false,
    CONSTRAINT operating_hours_weekday_check CHECK (weekday BETWEEN 0 AND 6),
    CONSTRAINT operating_hours_unique UNIQUE (outlet_id, weekday),
    CONSTRAINT operating_hours_value_check CHECK (
        is_closed = true OR (open_time IS NOT NULL AND close_time IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS subscription_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(30) NOT NULL UNIQUE,
    name varchar(100) NOT NULL,
    base_months smallint NOT NULL,
    bonus_months smallint NOT NULL DEFAULT 0,
    total_months smallint GENERATED ALWAYS AS (base_months + bonus_months) STORED,
    price numeric(12, 2) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT subscription_plans_months_check CHECK (base_months > 0 AND bonus_months >= 0),
    CONSTRAINT subscription_plans_price_check CHECK (price >= 0)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    outlet_id uuid NOT NULL REFERENCES outlets(id),
    plan_id uuid NOT NULL REFERENCES subscription_plans(id),
    start_date date NOT NULL,
    end_date date NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    amount numeric(12, 2),
    payment_reference varchar(255),
    created_by uuid REFERENCES dashboard_accounts(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT subscriptions_dates_check CHECK (end_date >= start_date),
    CONSTRAINT subscriptions_status_check CHECK (status IN ('ACTIVE', 'EXPIRED', 'CANCELLED'))
);

CREATE TABLE IF NOT EXISTS outlet_states (
    outlet_id uuid PRIMARY KEY REFERENCES outlets(id) ON DELETE CASCADE,
    vercel_status varchar(10) NOT NULL DEFAULT 'OFF',
    shopee_actual_status varchar(20) NOT NULL DEFAULT 'UNKNOWN',
    suspension_status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    suspension_reason text,
    suspended_at timestamptz,
    suspension_ends_at timestamptz,
    pause_until timestamptz,
    last_checked_at timestamptz,
    last_action_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT outlet_states_vercel_status_check CHECK (vercel_status IN ('ON', 'OFF')),
    CONSTRAINT outlet_states_shopee_status_check CHECK (
        shopee_actual_status IN ('ON', 'PAUSE', 'OFF', 'UNKNOWN')
    ),
    CONSTRAINT outlet_states_suspension_check CHECK (
        suspension_status IN ('ACTIVE', 'SUSPENDED')
    )
);

CREATE TABLE IF NOT EXISTS automation_logs (
    id bigserial PRIMARY KEY,
    outlet_id uuid NOT NULL REFERENCES outlets(id),
    checked_at timestamptz NOT NULL DEFAULT now(),
    suspension_status varchar(20) NOT NULL,
    subscription_status varchar(20) NOT NULL,
    vercel_status_before varchar(10) NOT NULL,
    shopee_status_before varchar(20) NOT NULL,
    target_status varchar(20) NOT NULL,
    action varchar(40) NOT NULL,
    shopee_status_after varchar(20),
    success boolean NOT NULL,
    error_message text,
    reason text
);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id bigserial PRIMARY KEY,
    admin_account_id uuid NOT NULL REFERENCES dashboard_accounts(id),
    outlet_id uuid REFERENCES outlets(id),
    action varchar(80) NOT NULL,
    old_value jsonb,
    new_value jsonb,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outlets_merchant_idx ON outlets (merchant_id);
CREATE INDEX IF NOT EXISTS outlets_portal_idx ON outlets (portal_id);
CREATE INDEX IF NOT EXISTS outlets_account_idx ON outlets (shopee_account_id);
CREATE INDEX IF NOT EXISTS subscriptions_outlet_end_idx ON subscriptions (outlet_id, end_date DESC);
CREATE INDEX IF NOT EXISTS automation_logs_outlet_checked_idx ON automation_logs (outlet_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS admin_audit_logs_outlet_created_idx ON admin_audit_logs (outlet_id, created_at DESC);

INSERT INTO subscription_plans (code, name, base_months, bonus_months, price)
VALUES
    ('3_MONTHS', 'Paket 3 Bulan', 3, 0, 90000),
    ('6_MONTHS', 'Paket 6 Bulan', 6, 1, 180000),
    ('12_MONTHS', 'Paket 12 Bulan', 12, 4, 360000)
ON CONFLICT (code) DO NOTHING;

INSERT INTO schema_migrations (version)
VALUES ('001_initial_schema')
ON CONFLICT (version) DO NOTHING;

