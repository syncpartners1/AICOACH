-- Apply only after the coaching_lead_submissions migration.
-- Lead contact facts do not create a work order or an AI invitation.
CREATE TABLE IF NOT EXISTS coaching_lead_contacts (
  submission_id UUID PRIMARY KEY REFERENCES coaching_lead_submissions(submission_id),
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  mobile_phone TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
