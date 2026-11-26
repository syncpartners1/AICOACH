-- Apply only after explicit migration approval. Additive, no client/profile changes.
BEGIN;
CREATE TABLE IF NOT EXISTS maps_invitations (
 id text PRIMARY KEY,
 code_hash text UNIQUE NOT NULL,
 label text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 redeemed_at timestamptz,
 device_hash text,
 revoked_at timestamptz,
 CHECK ((redeemed_at IS NULL) = (device_hash IS NULL))
);
CREATE TABLE IF NOT EXISTS maps_access_attempts (
 bucket text PRIMARY KEY,
 window_start timestamptz NOT NULL,
 attempts integer NOT NULL
);
COMMIT;
