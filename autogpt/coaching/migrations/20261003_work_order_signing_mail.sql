-- Work-order signing mail: additive columns only. Apply before deploying the code.
-- The drafts table and its status CHECK are not touched; the signed stage is derived
-- from work_order_links.
ALTER TABLE work_order_links
  ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS sent_to TEXT,
  ADD COLUMN IF NOT EXISTS signed_alert_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS signed_copy_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS signed_copy_to TEXT;
