-- Run in Cloud SQL aicoach_db before deploying the email status code.
-- Existing rows remain pending; no automatic resend is performed.
ALTER TABLE coaching_lead_submissions
  ADD COLUMN IF NOT EXISTS coach_email_state TEXT NOT NULL DEFAULT 'pending';
