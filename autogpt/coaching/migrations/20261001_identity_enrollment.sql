-- DRAFT REVIEW ONLY; coupled rollout. No legacy backfill.
BEGIN;
ALTER TABLE google_oauth_intents ADD COLUMN IF NOT EXISTS purpose text NOT NULL DEFAULT 'login';
ALTER TABLE google_oauth_intents ADD COLUMN IF NOT EXISTS profile_id uuid REFERENCES user_profiles(user_id) ON DELETE CASCADE;
ALTER TABLE google_oauth_intents ADD COLUMN IF NOT EXISTS recovery_hash text;
CREATE TABLE IF NOT EXISTS identity_link_confirmations (
 token_hash text PRIMARY KEY,browser_hash text NOT NULL,
 user_id uuid NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
 subject text NOT NULL,google_email text NOT NULL,source text NOT NULL,
 expires_at timestamptz NOT NULL,consumed_at timestamptz
);
CREATE TABLE IF NOT EXISTS identity_recovery_requests (
 token_hash text PRIMARY KEY,browser_hash text NOT NULL,mailbox text NOT NULL,
 code_hash text NOT NULL,attempts integer NOT NULL DEFAULT 0,
 code_expires_at timestamptz NOT NULL,email_verified_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),expires_at timestamptz NOT NULL,
 subject text,google_proven_at timestamptz,
 user_id uuid REFERENCES user_profiles(user_id) ON DELETE CASCADE,
 approved_at timestamptz,approval_expires_at timestamptz,denied_at timestamptz,consumed_at timestamptz
);
CREATE INDEX IF NOT EXISTS identity_recovery_mail_rate ON identity_recovery_requests(mailbox,created_at);
COMMIT;
