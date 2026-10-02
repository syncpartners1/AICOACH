-- Diagnostic-meeting (פגישת איבחון) stage per questionnaire lead.
-- Apply after the coaching_lead_submissions migration (already live). No row = new lead.
-- Rollback: DROP TABLE coaching_lead_stage; nothing else depends on it.
CREATE TABLE IF NOT EXISTS coaching_lead_stage (
  submission_id UUID PRIMARY KEY REFERENCES coaching_lead_submissions(submission_id),
  stage TEXT NOT NULL CHECK (stage IN ('booked','held','no_show','won','lost')),
  booking_event_id TEXT,
  meeting_start TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_coaching_lead_stage_event ON coaching_lead_stage(booking_event_id);
