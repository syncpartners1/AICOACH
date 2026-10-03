-- Run in Cloud SQL aicoach_db BEFORE merging the code that writes coaching_interest.
-- One new table and one index. Nothing existing is changed.
CREATE TABLE IF NOT EXISTS coaching_interest (
  interest_id UUID PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
  email TEXT NOT NULL CHECK (length(email) BETWEEN 3 AND 254),
  phone_e164 TEXT NOT NULL CHECK (length(phone_e164) BETWEEN 8 AND 20),
  source TEXT NOT NULL DEFAULT 'interest-page' CHECK (length(source) BETWEEN 1 AND 40),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS coaching_interest_phone_idx ON coaching_interest (phone_e164);
CREATE INDEX IF NOT EXISTS coaching_interest_created_idx ON coaching_interest (created_at DESC);
