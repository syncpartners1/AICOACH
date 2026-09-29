-- Coaching questionnaire intake. Apply to Cloud SQL before deploying app code.
-- Private server-side records; ClickUp is the coach-facing CRM, not the only copy.
CREATE TABLE IF NOT EXISTS coaching_lead_submissions (
  submission_id UUID PRIMARY KEY,
  email TEXT NOT NULL,
  name TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  verdict TEXT NOT NULL CHECK (verdict IN ('PASS', 'BORDERLINE', 'FAIL')),
  answers JSONB NOT NULL,
  clickup_state TEXT NOT NULL DEFAULT 'pending'
    CHECK (clickup_state IN ('pending', 'created', 'needs_review')),
  clickup_task_id TEXT,
  clickup_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_coaching_leads_state ON coaching_lead_submissions(clickup_state, created_at);
