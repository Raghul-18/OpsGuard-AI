-- OpsGuard AI - Initial Schema
-- Run this in the Supabase SQL editor.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- orders
CREATE TABLE IF NOT EXISTS orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id         TEXT NOT NULL,
    order_ref           TEXT,
    sku_id              TEXT,
    quantity            INTEGER,
    unit_price_inr      NUMERIC,
    payment_method      TEXT,
    destination_pincode TEXT,
    ordered_at          TIMESTAMPTZ,
    source              TEXT,
    source_record_id    TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT now(),
    raw_metadata        JSONB,
    UNIQUE (merchant_id, source, source_record_id, sku_id)
);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_orders ON orders
    USING (merchant_id = current_setting('app.merchant_id', true))
    WITH CHECK (merchant_id = current_setting('app.merchant_id', true));

-- shipments
CREATE TABLE IF NOT EXISTS shipments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id         TEXT NOT NULL,
    shipment_ref        TEXT,
    order_ref           TEXT,
    order_id            UUID REFERENCES orders(id) ON DELETE SET NULL,
    courier_name        TEXT,
    weight_declared_kg  NUMERIC,
    weight_charged_kg   NUMERIC,
    shipping_cost_inr   NUMERIC,
    status              TEXT,
    rto                 BOOLEAN DEFAULT FALSE,
    destination_pincode TEXT,
    source              TEXT,
    source_record_id    TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT now(),
    raw_metadata        JSONB,
    UNIQUE (merchant_id, source, source_record_id)
);

ALTER TABLE shipments ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_shipments ON shipments
    USING (merchant_id = current_setting('app.merchant_id', true))
    WITH CHECK (merchant_id = current_setting('app.merchant_id', true));

-- sku_master
CREATE TABLE IF NOT EXISTS sku_master (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id         TEXT NOT NULL,
    sku_id              TEXT,
    name                TEXT,
    cost_price_inr      NUMERIC,
    packaging_weight_g  NUMERIC,
    reorder_level       INTEGER,
    inventory_quantity  INTEGER,
    category            TEXT,
    source              TEXT,
    source_record_id    TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT now(),
    raw_metadata        JSONB,
    UNIQUE (merchant_id, sku_id)
);

ALTER TABLE sku_master ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_sku_master ON sku_master
    USING (merchant_id = current_setting('app.merchant_id', true))
    WITH CHECK (merchant_id = current_setting('app.merchant_id', true));

-- reconciliation_results
CREATE TABLE IF NOT EXISTS reconciliation_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id         TEXT NOT NULL,
    shipment_id         UUID REFERENCES shipments(id) ON DELETE CASCADE,
    discrepancy_type    TEXT,
    declared_value      NUMERIC,
    charged_value       NUMERIC,
    amount_disputed_inr NUMERIC,
    status              TEXT DEFAULT 'open',
    created_at          TIMESTAMPTZ DEFAULT now(),
    actioned_at         TIMESTAMPTZ,
    action_note         TEXT,
    UNIQUE (merchant_id, shipment_id, discrepancy_type)
);

ALTER TABLE reconciliation_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_reconciliation ON reconciliation_results
    USING (merchant_id = current_setting('app.merchant_id', true))
    WITH CHECK (merchant_id = current_setting('app.merchant_id', true));

-- agent_runs
CREATE TABLE IF NOT EXISTS agent_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id       TEXT NOT NULL,
    run_at            TIMESTAMPTZ DEFAULT now(),
    trigger           TEXT,
    data_window_days  INTEGER,
    shipments_scanned INTEGER,
    findings          JSONB,
    proposals         JSONB,
    reasoning         TEXT,
    status            TEXT DEFAULT 'running',
    error             TEXT
);

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_agent_runs ON agent_runs
    USING (merchant_id = current_setting('app.merchant_id', true))
    WITH CHECK (merchant_id = current_setting('app.merchant_id', true));

-- sync_jobs
CREATE TABLE IF NOT EXISTS sync_jobs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id    TEXT NOT NULL,
    connector      TEXT,
    status         TEXT DEFAULT 'pending',
    scheduled_at   TIMESTAMPTZ DEFAULT now(),
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ,
    row_count      INTEGER DEFAULT 0,
    error          TEXT
);

ALTER TABLE sync_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_sync_jobs ON sync_jobs
    USING (merchant_id = current_setting('app.merchant_id', true))
    WITH CHECK (merchant_id = current_setting('app.merchant_id', true));

-- Indexes
CREATE INDEX IF NOT EXISTS idx_orders_merchant ON orders(merchant_id);
CREATE INDEX IF NOT EXISTS idx_orders_sku ON orders(merchant_id, sku_id);
CREATE INDEX IF NOT EXISTS idx_orders_pincode ON orders(merchant_id, destination_pincode);
CREATE INDEX IF NOT EXISTS idx_shipments_merchant ON shipments(merchant_id);
CREATE INDEX IF NOT EXISTS idx_shipments_courier ON shipments(merchant_id, courier_name);
CREATE INDEX IF NOT EXISTS idx_shipments_order_ref ON shipments(merchant_id, order_ref);
CREATE INDEX IF NOT EXISTS idx_sku_master_merchant ON sku_master(merchant_id, sku_id);
CREATE INDEX IF NOT EXISTS idx_reconciliation_merchant ON reconciliation_results(merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_merchant ON agent_runs(merchant_id, run_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_merchant ON sync_jobs(merchant_id, connector);

-- Existing deployments: add inventory column if missing
ALTER TABLE sku_master ADD COLUMN IF NOT EXISTS inventory_quantity INTEGER;
