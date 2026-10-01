-- Apply in aicoach_db BEFORE merging/deploying booking receiver.
-- No historical backfill; does not create or alter calendar events.
CREATE TABLE IF NOT EXISTS booking_notifications (
 event_id TEXT PRIMARY KEY CHECK (length(event_id) BETWEEN 1 AND 512),
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 read_at TIMESTAMPTZ,
 email_state TEXT NOT NULL DEFAULT 'pending'
   CHECK (email_state IN ('pending','processing','accepted','failed','uncertain')),
 email_attempted_at TIMESTAMPTZ,
 email_updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS booking_notifications_newest_idx ON booking_notifications(created_at DESC,event_id DESC);
CREATE INDEX IF NOT EXISTS booking_notifications_unread_idx ON booking_notifications(created_at DESC) WHERE read_at IS NULL;
