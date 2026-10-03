-- Apply in aicoach_db BEFORE merging the phase 6.1 code. Idempotent; safe to run twice.
-- M017 (phase 6.1): explicit channel per saved session. NULL = unknown, never guessed.
-- Apply in aicoach_db BEFORE merging the 6.1 code (the code writes this column).
ALTER TABLE coaching_sessions ADD COLUMN IF NOT EXISTS channel TEXT
  CHECK (channel IS NULL OR channel IN ('telegram', 'pwa', 'manual'));
-- Careful backfill from facts already stored. Rows that match nothing stay NULL.
UPDATE coaching_sessions SET channel = 'manual'
 WHERE channel IS NULL AND (is_manual IS TRUE OR client_id LIKE 'admin\_manual\_%');
UPDATE coaching_sessions SET channel = 'telegram'
 WHERE channel IS NULL AND client_id LIKE 'telegram\_%';
UPDATE coaching_sessions SET channel = 'pwa'
 WHERE channel IS NULL AND client_id LIKE 'web\_%';
CREATE OR REPLACE FUNCTION finalize_claimed_coaching_session(
  p_session_id TEXT, p_version BIGINT, p_lease_token UUID,
  p_summary JSONB, p_key_results JSONB DEFAULT '[]'::jsonb,
  p_obstacles JSONB DEFAULT '[]'::jsonb
) RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
  claimed active_coaching_sessions%ROWTYPE;
BEGIN
  SELECT * INTO claimed FROM active_coaching_sessions
   WHERE session_id = p_session_id FOR UPDATE;
  IF NOT FOUND OR claimed.status <> 'finalizing'
     OR claimed.version <> p_version OR claimed.lease_token IS DISTINCT FROM p_lease_token
     OR claimed.lease_until <= NOW() THEN
    RETURN FALSE;
  END IF;
  IF p_summary->>'session_id' IS DISTINCT FROM p_session_id
     OR p_summary->>'user_id' IS DISTINCT FROM claimed.user_id::text
     OR p_summary->>'client_id' IS DISTINCT FROM claimed.client_id
     OR p_summary->'raw_conversation' IS DISTINCT FROM claimed.transcript THEN
    RAISE EXCEPTION 'Summary does not match claimed session';
  END IF;
  INSERT INTO coaching_sessions
      (session_id, client_id, user_id, timestamp, focus_goal, environmental_changes,
       mood_indicator, alert_level, alert_reason, summary_for_coach, raw_conversation,
       extraction_raw, channel)
  VALUES (p_session_id, claimed.client_id, claimed.user_id,
          COALESCE((p_summary->>'timestamp')::timestamptz, NOW()),
          p_summary->>'focus_goal', p_summary->>'environmental_changes',
          p_summary->>'mood_indicator', p_summary->>'alert_level',
          p_summary->>'alert_reason', p_summary->>'summary_for_coach',
          claimed.transcript, p_summary->>'extraction_raw', claimed.channel)
  ON CONFLICT (session_id) DO NOTHING;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Session summary already exists';
  END IF;
  INSERT INTO key_results (session_id, kr_id, description, status_pct, status_color)
    SELECT p_session_id, x.kr_id, x.description, x.status_pct, x.status_color
      FROM jsonb_to_recordset(p_key_results) AS x(
        kr_id INTEGER, description TEXT, status_pct INTEGER, status_color TEXT);
  INSERT INTO obstacles (session_id, description, reported_at, resolved)
    SELECT p_session_id, x.description, x.reported_at, COALESCE(x.resolved, FALSE)
      FROM jsonb_to_recordset(p_obstacles) AS x(
        description TEXT, reported_at TIMESTAMPTZ, resolved BOOLEAN);
  UPDATE active_coaching_sessions
     SET status = 'completed', version = version + 1,
         lease_token = NULL, lease_until = NULL, updated_at = NOW()
   WHERE session_id = p_session_id;
  RETURN TRUE;
END;
$$;
