-- Review-only prerequisite. No automatic trusted-credential backfill.
-- Owner read-only preflight confirms user_profiles.user_id UUID.
BEGIN;
CREATE TABLE IF NOT EXISTS google_oauth_intents (
 state_hash text PRIMARY KEY,
 browser_hash text NOT NULL,
 nonce text NOT NULL,
 pkce_verifier text NOT NULL,
 return_to text NOT NULL,
 expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS google_oauth_intents_expiry ON google_oauth_intents(expires_at);
CREATE TABLE IF NOT EXISTS google_login_credentials (
 subject text PRIMARY KEY,
 user_id uuid NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
 verified_at timestamptz NOT NULL,
 source text NOT NULL CHECK (source IN ('telegram_google_dual_proof','approved_recovery','passkey_google_dual_proof')),
 revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS google_login_credentials_user ON google_login_credentials(user_id);
COMMIT;
-- NO INSERT SELECT from legacy google_id/email. Future dual-proof enrollment only.
