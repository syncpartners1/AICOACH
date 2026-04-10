-- ============================================================
-- ABN Consulting AI Co-Navigator — Supabase Database Schema
-- Run this in your Supabase project's SQL Editor
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. USER PROFILES
-- Phone number is MANDATORY for every user regardless of sign-up method.
-- account_status: active | pending | suspended | archived
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
  user_id           UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  name              TEXT    NOT NULL,
  phone_number      TEXT    NOT NULL UNIQUE,       -- mandatory for all users
  email             TEXT    UNIQUE,                -- NULL for phone/Telegram-only accounts
  password_hash     TEXT,                          -- NULL for Google/phone/Telegram accounts
  google_id         TEXT    UNIQUE,                -- NULL for non-Google accounts
  telegram_user_id  BIGINT  UNIQUE,                -- linked Telegram account
  whatsapp_user_id  TEXT    UNIQUE,                -- linked WhatsApp number (normalized E.164)
  is_admin          BOOLEAN NOT NULL DEFAULT FALSE,
  account_status    TEXT    NOT NULL DEFAULT 'active'
                            CHECK (account_status IN ('active','pending','suspended','archived')),
  language          TEXT    NOT NULL DEFAULT 'en'
                            CHECK (language IN ('en','he')),
  suspended_at      TIMESTAMPTZ,
  suspended_reason  TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_email      ON user_profiles(email);
CREATE INDEX IF NOT EXISTS idx_user_google     ON user_profiles(google_id);
CREATE INDEX IF NOT EXISTS idx_user_phone      ON user_profiles(phone_number);
CREATE INDEX IF NOT EXISTS idx_user_telegram   ON user_profiles(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_user_whatsapp   ON user_profiles(whatsapp_user_id);
CREATE INDEX IF NOT EXISTS idx_user_status     ON user_profiles(account_status);

-- ============================================================
-- 2. OBJECTIVES  (user's ongoing OKR plan)
-- ============================================================
CREATE TABLE IF NOT EXISTS objectives (
  objective_id  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID    NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  title         TEXT    NOT NULL,
  description   TEXT    NOT NULL DEFAULT '',
  status        TEXT    NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'archived', 'on_hold')),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_objectives_user ON objectives(user_id, status);

-- ============================================================
-- 3. USER KEY RESULTS  (master KR list, per objective)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_key_results (
  kr_id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  objective_id  UUID    NOT NULL REFERENCES objectives(objective_id) ON DELETE CASCADE,
  user_id       UUID    NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  description   TEXT    NOT NULL,
  status        TEXT    NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'archived', 'on_hold')),
  current_pct   INTEGER NOT NULL DEFAULT 0 CHECK (current_pct BETWEEN 0 AND 100),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ukr_objective ON user_key_results(objective_id);
CREATE INDEX IF NOT EXISTS idx_ukr_user      ON user_key_results(user_id, status);

-- ============================================================
-- 4. CLIENTS  (legacy identifier, kept for dashboard compatibility)
-- ============================================================
CREATE TABLE IF NOT EXISTS clients (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id  TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  email      TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 5. COACHING SESSIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS coaching_sessions (
  id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id            TEXT    UNIQUE NOT NULL,
  client_id             TEXT    NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
  user_id               UUID    REFERENCES user_profiles(user_id) ON DELETE SET NULL,
  timestamp             TIMESTAMPTZ DEFAULT NOW(),
  focus_goal            TEXT,
  environmental_changes TEXT,
  mood_indicator        TEXT,
  alert_level           TEXT    CHECK (alert_level IN ('green', 'yellow', 'red')),
  alert_reason          TEXT,
  summary_for_coach     TEXT,
  raw_conversation      JSONB
);

CREATE INDEX IF NOT EXISTS idx_sessions_client_id ON coaching_sessions(client_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id   ON coaching_sessions(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_timestamp  ON coaching_sessions(timestamp DESC);

-- ============================================================
-- 6. SESSION KEY RESULTS  (snapshot per session, not master plan)
-- ============================================================
CREATE TABLE IF NOT EXISTS key_results (
  id           UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   TEXT    NOT NULL REFERENCES coaching_sessions(session_id) ON DELETE CASCADE,
  kr_id        INTEGER NOT NULL,
  description  TEXT    NOT NULL,
  status_pct   INTEGER CHECK (status_pct BETWEEN 0 AND 100),
  status_color TEXT    CHECK (status_color IN ('green', 'yellow', 'red'))
);

CREATE INDEX IF NOT EXISTS idx_kr_session_id ON key_results(session_id);

-- ============================================================
-- 7. SESSION OBSTACLES
-- ============================================================
CREATE TABLE IF NOT EXISTS obstacles (
  id           UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   TEXT    NOT NULL REFERENCES coaching_sessions(session_id) ON DELETE CASCADE,
  description  TEXT    NOT NULL,
  reported_at  TIMESTAMPTZ DEFAULT NOW(),
  resolved     BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_obstacles_session_id ON obstacles(session_id);

-- ============================================================
-- 8. WEEKLY PLANS  (one per user per week, keyed by Monday date)
-- ============================================================
CREATE TABLE IF NOT EXISTS weekly_plans (
  plan_id        UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID  NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  week_start     DATE  NOT NULL,  -- defaults to Sunday
  week_end       DATE,            -- defaults to Saturday (6 days after week_start)
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  updated_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_plans_user ON weekly_plans(user_id, week_start DESC);

-- ============================================================
-- 9. WEEKLY KR ACTIVITIES  (planned activities + progress per KR per week)
-- ============================================================
CREATE TABLE IF NOT EXISTS weekly_kr_activities (
  activity_id        UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id            UUID    NOT NULL REFERENCES weekly_plans(plan_id) ON DELETE CASCADE,
  kr_id              UUID    NOT NULL REFERENCES user_key_results(kr_id) ON DELETE CASCADE,
  planned_activities TEXT    NOT NULL DEFAULT '',
  progress_update    TEXT    NOT NULL DEFAULT '',
  insights           TEXT    NOT NULL DEFAULT '',
  gaps               TEXT    NOT NULL DEFAULT '',
  corrective_actions TEXT    NOT NULL DEFAULT '',
  current_pct        INTEGER CHECK (current_pct BETWEEN 0 AND 100),
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (plan_id, kr_id)
);

CREATE INDEX IF NOT EXISTS idx_wkra_plan ON weekly_kr_activities(plan_id);
CREATE INDEX IF NOT EXISTS idx_wkra_kr   ON weekly_kr_activities(kr_id);

-- ============================================================
-- 10. DAILY HIGHLIGHTS  (key highlights by day of week)
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_highlights (
  highlight_id UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID  NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  week_start   DATE  NOT NULL,
  day_of_week  TEXT  NOT NULL
                     CHECK (day_of_week IN ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')),
  highlight    TEXT  NOT NULL DEFAULT '',
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, week_start, day_of_week)
);

CREATE INDEX IF NOT EXISTS idx_daily_highlights_user ON daily_highlights(user_id, week_start DESC);

-- ============================================================
-- 11. INVITES  (admin-generated program invitations)
-- ============================================================
CREATE TABLE IF NOT EXISTS invites (
  invite_id   UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  token       TEXT  UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex'),
  invited_by  UUID  REFERENCES user_profiles(user_id) ON DELETE SET NULL,
  name        TEXT,                -- pre-filled name hint (optional)
  email       TEXT,                -- pre-filled email hint (optional)
  phone       TEXT,                -- pre-filled phone hint (optional)
  note        TEXT,                -- private note from admin
  used_at     TIMESTAMPTZ,
  used_by     UUID  REFERENCES user_profiles(user_id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  expires_at  TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days')
);

CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token);

-- ============================================================
-- Row Level Security — service role only
-- ============================================================
ALTER TABLE user_profiles        ENABLE ROW LEVEL SECURITY;
ALTER TABLE objectives            ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_key_results      ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients               ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaching_sessions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE key_results           ENABLE ROW LEVEL SECURITY;
ALTER TABLE obstacles             ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_plans          ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_kr_activities  ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_highlights      ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites               ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_only ON user_profiles;
DROP POLICY IF EXISTS service_only ON objectives;
DROP POLICY IF EXISTS service_only ON user_key_results;
DROP POLICY IF EXISTS service_only ON clients;
DROP POLICY IF EXISTS service_only ON coaching_sessions;
DROP POLICY IF EXISTS service_only ON key_results;
DROP POLICY IF EXISTS service_only ON obstacles;
DROP POLICY IF EXISTS service_only ON weekly_plans;
DROP POLICY IF EXISTS service_only ON weekly_kr_activities;
DROP POLICY IF EXISTS service_only ON daily_highlights;
DROP POLICY IF EXISTS service_only ON invites;

CREATE POLICY service_only ON user_profiles        USING (auth.role() = 'service_role');
CREATE POLICY service_only ON objectives            USING (auth.role() = 'service_role');
CREATE POLICY service_only ON user_key_results      USING (auth.role() = 'service_role');
CREATE POLICY service_only ON clients               USING (auth.role() = 'service_role');
CREATE POLICY service_only ON coaching_sessions     USING (auth.role() = 'service_role');
CREATE POLICY service_only ON key_results           USING (auth.role() = 'service_role');
CREATE POLICY service_only ON obstacles             USING (auth.role() = 'service_role');
CREATE POLICY service_only ON weekly_plans          USING (auth.role() = 'service_role');
CREATE POLICY service_only ON weekly_kr_activities  USING (auth.role() = 'service_role');
CREATE POLICY service_only ON daily_highlights      USING (auth.role() = 'service_role');
CREATE POLICY service_only ON invites               USING (auth.role() = 'service_role');

-- ============================================================
-- MIGRATIONS  (safe to re-run — all use IF NOT EXISTS / IF EXISTS)
-- ============================================================

-- M001: bilingual support — add language preference to user profiles
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en'
             CHECK (language IN ('en', 'he'));

-- M002: Telegram registration — add telegram_user_id column (if not present from schema v1)
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS telegram_user_id BIGINT UNIQUE;

CREATE INDEX IF NOT EXISTS idx_user_telegram ON user_profiles(telegram_user_id);

-- M003: pending approval workflow — extend account_status check constraint to include 'pending'
--       Run this in your Supabase SQL Editor if you get a CHECK constraint violation on account_status.
ALTER TABLE user_profiles
  DROP CONSTRAINT IF EXISTS user_profiles_account_status_check;

ALTER TABLE user_profiles
  ADD CONSTRAINT user_profiles_account_status_check
  CHECK (account_status IN ('active','pending','suspended','archived'));

-- M004: coaching_learnings — stores AI-generated insights extracted from session transcripts.
--       Used to inject coaching patterns into new sessions for continuous UX improvement.
CREATE TABLE IF NOT EXISTS coaching_learnings (
    learning_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    sessions_analyzed  INTEGER NOT NULL DEFAULT 0,
    scope              TEXT NOT NULL DEFAULT 'global',  -- 'global' or a user_id for per-user insights
    insights           JSONB NOT NULL DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_coaching_learnings_scope_generated
    ON coaching_learnings (scope, generated_at DESC);

ALTER TABLE coaching_learnings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_coaching_learnings" ON coaching_learnings;
CREATE POLICY "service_role_all_coaching_learnings"
    ON coaching_learnings FOR ALL
    USING (auth.role() = 'service_role');

-- M005: telegram_sessions — persists active AI coaching sessions across Railway restarts.
--       Keyed by telegram_user_id so it survives pod recycling.
CREATE TABLE IF NOT EXISTS telegram_sessions (
    telegram_user_id   BIGINT PRIMARY KEY,
    session_id         TEXT NOT NULL,
    client_id          TEXT NOT NULL,
    client_name        TEXT NOT NULL,
    user_id            TEXT,
    lang               TEXT NOT NULL DEFAULT 'en',
    system_prompt      TEXT NOT NULL DEFAULT '',
    message_history    JSONB NOT NULL DEFAULT '[]',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE telegram_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_telegram_sessions" ON telegram_sessions;
CREATE POLICY "service_role_all_telegram_sessions"
    ON telegram_sessions FOR ALL
    USING (auth.role() = 'service_role');

-- M006: coach session notes and manual session records
ALTER TABLE coaching_sessions ADD COLUMN IF NOT EXISTS coach_notes TEXT;
ALTER TABLE coaching_sessions ADD COLUMN IF NOT EXISTS is_manual BOOLEAN DEFAULT false;

-- M007: sales funnel leads (non-registered Telegram prospects)
CREATE TABLE IF NOT EXISTS funnel_leads (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_user_id BIGINT NOT NULL UNIQUE,
  username         TEXT,
  q1_answer        TEXT,
  q2_answer        TEXT,
  q3_answer        TEXT,
  link_clicked     BOOLEAN NOT NULL DEFAULT false,
  reminder_sent    BOOLEAN NOT NULL DEFAULT false,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_funnel_leads_tg ON funnel_leads(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_funnel_leads_reminder ON funnel_leads(reminder_sent, link_clicked, created_at);

ALTER TABLE funnel_leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_funnel_leads" ON funnel_leads;
CREATE POLICY "service_role_all_funnel_leads"
    ON funnel_leads FOR ALL
    USING (auth.role() = 'service_role');

-- M008: coaching program application tracking
ALTER TABLE funnel_leads ADD COLUMN IF NOT EXISTS applied BOOLEAN DEFAULT false;
