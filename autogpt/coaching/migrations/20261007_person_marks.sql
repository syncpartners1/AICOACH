-- Funnel step 3: manual marks, notes and pending join invitations. Three NEW tables, nothing existing is changed.
-- Apply in Cloud SQL aicoach_db BEFORE deploying the code that writes them (PRs 5c to 5f). Nothing reads them yet.
-- No foreign key to people: the people rows are rebuilt by the sync, and a mark must never vanish with them.
-- stable_key is the person's phone (+E.164) or, if there is none, the email, so a mark can be re-attached after a merge or split.
-- Rollback: DROP TABLE person_marks, person_notes, join_invites_pending; nothing else depends on them.
CREATE TABLE IF NOT EXISTS person_marks (
  mark_id BIGSERIAL PRIMARY KEY,
  person_id UUID NOT NULL,
  stable_key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('intro', 'diagnostic', 'not_lead')),
  state TEXT NOT NULL CHECK (state IN ('held', 'no_show', 'cleared', 'on', 'off')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT NOT NULL DEFAULT 'admin',
  CHECK ((kind = 'not_lead' AND state IN ('on', 'off')) OR (kind <> 'not_lead' AND state IN ('held', 'no_show', 'cleared')))
);
-- The current value is the latest row per (person_id, kind); history is every row.
CREATE INDEX IF NOT EXISTS person_marks_latest ON person_marks (person_id, kind, mark_id DESC);
CREATE INDEX IF NOT EXISTS person_marks_stable_key ON person_marks (stable_key);
CREATE TABLE IF NOT EXISTS person_notes (
  note_id BIGSERIAL PRIMARY KEY,
  person_id UUID NOT NULL,
  stable_key TEXT NOT NULL,
  body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
  hidden BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT NOT NULL DEFAULT 'admin'
);
CREATE INDEX IF NOT EXISTS person_notes_person ON person_notes (person_id, created_at DESC);
CREATE TABLE IF NOT EXISTS join_invites_pending (
  pending_id BIGSERIAL PRIMARY KEY,
  person_id UUID NOT NULL,
  stable_key TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL,
  phone TEXT,
  language TEXT NOT NULL DEFAULT 'he' CHECK (language IN ('he', 'en')),
  note TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'sent', 'cancelled')),
  invite_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ
);
-- At most one open request per person.
CREATE UNIQUE INDEX IF NOT EXISTS join_invites_one_open ON join_invites_pending (person_id) WHERE status IN ('pending', 'sending');
