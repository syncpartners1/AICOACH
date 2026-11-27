-- Apply only after the separate read-only preflight was reviewed.
-- No identity changes or automatic credential revocation.
BEGIN;
DO $$ BEGIN
 IF current_database() <> 'aicoach_db' THEN RAISE EXCEPTION 'Wrong database'; END IF;
END $$;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
LOCK TABLE google_login_credentials IN SHARE ROW EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM google_login_credentials WHERE revoked_at IS NULL
            GROUP BY user_id HAVING count(*)>1) THEN
  RAISE EXCEPTION 'Multiple active Google credentials exist; manual review required';
 END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS google_login_one_active_user
 ON google_login_credentials(user_id) WHERE revoked_at IS NULL;
COMMIT;
