-- Apply after work_orders.sql (PR 1), before enabling signing routes.
CREATE TABLE IF NOT EXISTS work_order_links (
  token_digest TEXT PRIMARY KEY,
  order_id UUID NOT NULL REFERENCES work_order_drafts(order_id),
  payment_schedule TEXT NOT NULL CHECK (length(payment_schedule) BETWEEN 3 AND 500),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  signed_at TIMESTAMPTZ,
  signer_name TEXT,
  signer_role TEXT,
  signature_png BYTEA,
  signed_pdf BYTEA,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS work_order_links_order_id ON work_order_links(order_id);
