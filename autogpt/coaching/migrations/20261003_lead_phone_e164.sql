-- Run in Cloud SQL aicoach_db BEFORE deploying the code that writes phone_e164.
-- One new nullable column. Existing rows stay NULL; nothing is rewritten or dropped.
ALTER TABLE coaching_lead_submissions
  ADD COLUMN IF NOT EXISTS phone_e164 TEXT;
CREATE INDEX IF NOT EXISTS coaching_lead_submissions_phone_e164_idx
  ON coaching_lead_submissions (phone_e164) WHERE phone_e164 IS NOT NULL;
