-- Apply in aicoach_db BEFORE merging assignment code. No historical backfill.
ALTER TABLE coaching_sessions ADD COLUMN IF NOT EXISTS meeting_number INTEGER;
ALTER TABLE coaching_sessions ADD COLUMN IF NOT EXISTS leading_value_snapshot TEXT;
CREATE TABLE IF NOT EXISTS session_assignments (
 action_id UUID PRIMARY KEY,
 user_id UUID NOT NULL REFERENCES user_profiles(user_id),
 session_id TEXT NOT NULL REFERENCES coaching_sessions(session_id),
 position INTEGER NOT NULL,
 description TEXT NOT NULL CHECK (length(description) BETWEEN 1 AND 500),
 due_date DATE,
 agreement_source TEXT NOT NULL CHECK (agreement_source IN ('coach_recorded','participant_confirmed')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 archived_at TIMESTAMPTZ,
 UNIQUE(session_id, position)
);
CREATE TABLE IF NOT EXISTS session_assignment_reports (
 report_id UUID PRIMARY KEY,
 action_id UUID NOT NULL REFERENCES session_assignments(action_id),
 user_id UUID NOT NULL REFERENCES user_profiles(user_id),
 completed BOOLEAN NOT NULL,
 channel TEXT NOT NULL,
 request_id TEXT NOT NULL,
 reported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(user_id, channel, request_id)
);
