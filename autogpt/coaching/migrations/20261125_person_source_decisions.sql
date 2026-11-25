-- Additive. Run before code rollout. No existing person/invite/client row is changed.
-- No FK to derived people: history survives sync; strict anchors prevent transfer on splits.
CREATE TABLE IF NOT EXISTS person_source_decisions (
  decision_id BIGSERIAL PRIMARY KEY,
  person_id UUID NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('unset','tut','non_tut')),
  anchors JSONB NOT NULL CHECK (jsonb_typeof(anchors)='array' AND jsonb_array_length(anchors)>0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT NOT NULL DEFAULT 'admin'
);
CREATE INDEX IF NOT EXISTS person_source_person ON person_source_decisions(person_id, decision_id DESC);
-- Roll back application first. Keep history unless separately approved for deletion.

-- Nullable only for pre-existing pending requests; new code always stores a revision.
ALTER TABLE join_invites_pending ADD COLUMN IF NOT EXISTS source_revision TEXT;

-- Renewal audit: no tokens/registration URLs. Uncertain SMTP outcome blocks retries.
CREATE TABLE IF NOT EXISTS invite_renewal_attempts (
  renewal_id BIGSERIAL PRIMARY KEY,
  invite_id UUID NOT NULL,
  person_id UUID NOT NULL,
  email TEXT NOT NULL,
  old_expires_at TIMESTAMPTZ NOT NULL,
  new_expires_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('sending','sent','uncertain')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS invite_renewal_by_invite ON invite_renewal_attempts(invite_id,renewal_id DESC);
