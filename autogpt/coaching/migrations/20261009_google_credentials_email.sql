-- Show the linked Google address in the admin users table. One nullable column, no change to user_profiles.
-- Apply in Cloud SQL aicoach_db BEFORE deploying the code that writes and reads it.
-- The backfill only fills the new column of credentials that already exist, from the address the link confirmation stored
-- when the user proved the link. It creates no credential and links no one (no legacy backfill of google_id, email or phone).
-- Rollback: ALTER TABLE google_login_credentials DROP COLUMN google_email; nothing else depends on it.
ALTER TABLE google_login_credentials ADD COLUMN IF NOT EXISTS google_email text;
UPDATE google_login_credentials c SET google_email = x.google_email
FROM (SELECT DISTINCT ON (user_id, subject) user_id, subject, google_email
      FROM identity_link_confirmations WHERE consumed_at IS NOT NULL
      ORDER BY user_id, subject, consumed_at DESC) x
WHERE c.user_id = x.user_id AND c.subject = x.subject AND c.google_email IS NULL;
