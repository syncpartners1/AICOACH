-- GATED REHEARSAL, NOT APPLY. Creates index only inside a rolled-back transaction.
-- Run only after preflight review and explicit approval. No credential rows changed.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
DO $$ BEGIN
 IF current_database()<>'aicoach_db' THEN RAISE EXCEPTION 'Wrong database'; END IF;
 IF current_setting('server_version_num')::int<>150019 THEN RAISE EXCEPTION 'Review target version first'; END IF;
END $$;
LOCK TABLE google_login_credentials IN SHARE ROW EXCLUSIVE MODE;
SELECT 'BEFORE' AS phase,count(*) AS all_credentials,
 count(*) FILTER(WHERE revoked_at IS NULL) AS active_credentials
FROM google_login_credentials;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM google_login_credentials WHERE revoked_at IS NULL GROUP BY user_id HAVING count(*)>1)
 THEN RAISE EXCEPTION 'Duplicate active Google credentials, stop'; END IF;
 IF to_regclass('google_login_one_active_user') IS NOT NULL
 THEN RAISE EXCEPTION 'Index already present, inspect instead of rehearsing'; END IF;
END $$;
CREATE UNIQUE INDEX google_login_one_active_user ON google_login_credentials(user_id) WHERE revoked_at IS NULL;
SELECT 'INSIDE_ROLLBACK_ONLY' AS phase,i.indisunique,i.indisvalid,
 pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index i WHERE i.indexrelid=to_regclass('google_login_one_active_user');
ROLLBACK;
SELECT current_database() AS database_name,current_setting('server_version') AS postgres_version,
 to_regclass('google_login_one_active_user') IS NULL AS rehearsal_index_absent,
 count(*) AS all_credentials,count(*) FILTER(WHERE revoked_at IS NULL) AS active_credentials
FROM google_login_credentials;
-- On any earlier error, ROLLBACK before doing anything else. Never COMMIT this rehearsal.
