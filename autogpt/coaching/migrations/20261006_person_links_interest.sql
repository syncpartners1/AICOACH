-- Run in Cloud SQL aicoach_db BEFORE merging the code that links interest-form rows to people.
-- Widens one CHECK on person_links (a table the people sync rebuilds) to allow the source 'coaching_interest'.
-- No source table is touched and no row is changed: every existing row already satisfies the wider rule.
ALTER TABLE person_links DROP CONSTRAINT IF EXISTS person_links_source_table_check;
ALTER TABLE person_links ADD CONSTRAINT person_links_source_table_check CHECK (source_table IN
  ('coaching_lead_submissions', 'booking_notifications', 'work_order_drafts', 'invites', 'user_profiles', 'coaching_interest'));
