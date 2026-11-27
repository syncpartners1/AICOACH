-- Additive name history only. No backfill or edits to existing names.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = public;
DO $$ BEGIN
 IF current_database() <> 'aicoach_db' THEN RAISE EXCEPTION 'Wrong database; expected aicoach_db'; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aicoach_user') THEN RAISE EXCEPTION 'Missing application role'; END IF;
END $$;
CREATE TABLE IF NOT EXISTS person_name_events (
 event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID REFERENCES user_profiles(user_id) ON DELETE CASCADE,
 submission_id UUID REFERENCES coaching_lead_submissions(submission_id) ON DELETE CASCADE,
 previous_name TEXT NOT NULL,
 new_name TEXT NOT NULL,
 changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 actor_kind TEXT NOT NULL CHECK(actor_kind='shared_admin_session'),
 admin_account TEXT NOT NULL,
 source TEXT NOT NULL CHECK(source='admin_person_card'),
 CHECK ((user_id IS NOT NULL)::int + (submission_id IS NOT NULL)::int = 1)
);
CREATE INDEX IF NOT EXISTS person_name_events_user_time ON person_name_events(user_id,changed_at);
CREATE INDEX IF NOT EXISTS person_name_events_lead_time ON person_name_events(submission_id,changed_at);
REVOKE ALL ON person_name_events FROM PUBLIC;
ALTER TABLE person_name_events OWNER TO aicoach_user;
GRANT SELECT, INSERT ON person_name_events TO aicoach_user;
COMMIT;
