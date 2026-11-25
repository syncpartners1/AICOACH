-- aicoach_db: additive manual meeting bookkeeping, before code deployment.
-- No calendar, SMTP, program counts or historical session writes.
BEGIN;
ALTER TABLE booking_notifications ADD COLUMN IF NOT EXISTS meeting_status TEXT NOT NULL DEFAULT 'unset'
 CHECK (meeting_status IN ('unset','held','cancelled','needs_booking'));
ALTER TABLE booking_notifications ADD COLUMN IF NOT EXISTS status_revision BIGINT NOT NULL DEFAULT 0 CHECK (status_revision>=0);
ALTER TABLE booking_notifications ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS booking_meeting_status_audit (
 id BIGSERIAL PRIMARY KEY,
 event_id TEXT NOT NULL REFERENCES booking_notifications(event_id),
 previous_status TEXT NOT NULL CHECK (previous_status IN ('unset','held','cancelled','needs_booking')),
 new_status TEXT NOT NULL CHECK (new_status IN ('unset','held','cancelled','needs_booking')),
 revision BIGINT NOT NULL CHECK (revision>0),
 changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(event_id,revision)
);
COMMIT;
