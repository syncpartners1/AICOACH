-- Additive professional-track metadata. Run dry-run first, apply only after review.
-- No existing client row is updated; legacy engine curriculum and phase remain intact.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = public;
DO $$ BEGIN
 IF current_database() <> 'aicoach_db' THEN RAISE EXCEPTION 'Wrong database; expected aicoach_db'; END IF;
END $$;
ALTER TABLE coaching_programs ADD COLUMN IF NOT EXISTS coaching_track TEXT;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='coaching_programs'::regclass
                AND conname='coaching_programs_professional_track_check') THEN
  ALTER TABLE coaching_programs ADD CONSTRAINT coaching_programs_professional_track_check
   CHECK (coaching_track IN ('personal','family_finance','career','startup','business_mgmt','ptg_crisis'));
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS coaching_track_events (
 event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
 previous_track TEXT CHECK(previous_track IN ('personal','family_finance','career','startup','business_mgmt','ptg_crisis')),
 new_track TEXT NOT NULL CHECK(new_track IN ('personal','family_finance','career','startup','business_mgmt','ptg_crisis')),
 changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 source TEXT NOT NULL DEFAULT 'admin_program_metadata' CHECK(source='admin_program_metadata')
);
CREATE INDEX IF NOT EXISTS coaching_track_events_user_time ON coaching_track_events(user_id,changed_at);
REVOKE ALL ON coaching_track_events FROM PUBLIC;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aicoach_user') THEN
  RAISE EXCEPTION 'Application role aicoach_user missing; stop and review';
 END IF;
END $$;
ALTER TABLE coaching_track_events OWNER TO aicoach_user;
GRANT SELECT, INSERT ON coaching_track_events TO aicoach_user;
COMMIT;
