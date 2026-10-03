-- People and identifiers for the funnel screen. Four NEW tables, nothing existing is changed.
-- Apply in Cloud SQL aicoach_db BEFORE deploying the code that fills them (sync_people).
-- Rollback: DROP TABLE people_review, person_links, person_identifiers, people; nothing else depends on them.
CREATE TABLE IF NOT EXISTS people (
  person_id UUID PRIMARY KEY,
  display_name TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS person_identifiers (
  person_id UUID NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('phone', 'email')),
  value TEXT NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (person_id, kind, value)
);
-- One person per phone number. An email may sit on two people only when their phones differ (see people_review).
CREATE UNIQUE INDEX IF NOT EXISTS person_identifiers_phone_unique ON person_identifiers (value) WHERE kind = 'phone';
CREATE INDEX IF NOT EXISTS person_identifiers_lookup ON person_identifiers (kind, value);
CREATE TABLE IF NOT EXISTS person_links (
  person_id UUID NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
  source_table TEXT NOT NULL CHECK (source_table IN
    ('coaching_lead_submissions', 'booking_notifications', 'work_order_drafts', 'invites', 'user_profiles')),
  source_key TEXT NOT NULL,
  PRIMARY KEY (source_table, source_key)
);
CREATE INDEX IF NOT EXISTS person_links_person ON person_links (person_id);
CREATE TABLE IF NOT EXISTS people_review (
  review_id BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('email_multiple_phones')),
  value TEXT NOT NULL,
  person_ids UUID[] NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
