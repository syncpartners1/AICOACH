-- Apply to the active Cloud SQL database before enabling /admin/work-orders.
-- Separate migration, not a change to the older Supabase setup script.
CREATE TABLE IF NOT EXISTS work_order_prices (
  price_key TEXT PRIMARY KEY,
  amount_agorot BIGINT NOT NULL CHECK (amount_agorot > 0),
  vat_mode TEXT NOT NULL CHECK (vat_mode IN ('plus_vat','vat_included')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS work_order_drafts (
  order_id UUID PRIMARY KEY,
  customer_name TEXT NOT NULL,
  customer_identity TEXT NOT NULL,
  organization_contact TEXT NOT NULL DEFAULT '',
  customer_email TEXT NOT NULL,
  customer_phone TEXT NOT NULL,
  customer_address TEXT NOT NULL,
  track TEXT NOT NULL CHECK (track IN ('personal','family','business')),
  plan TEXT NOT NULL CHECK (plan IN ('full','intro','per_session')),
  price_key TEXT NOT NULL,
  amount_agorot BIGINT NOT NULL CHECK (amount_agorot > 0),
  vat_mode TEXT NOT NULL CHECK (vat_mode IN ('plus_vat','vat_included')),
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status='draft'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- This table is private to the application DB connection; no public REST policy.
