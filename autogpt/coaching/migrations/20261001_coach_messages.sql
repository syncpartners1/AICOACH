-- Apply in aicoach_db BEFORE deploying the coach inbox patch. No historical backfill.
CREATE TABLE IF NOT EXISTS coach_messages (
 message_id UUID PRIMARY KEY,
 user_id UUID NOT NULL REFERENCES user_profiles(user_id),
 sender_name TEXT NOT NULL,
 channel TEXT NOT NULL CHECK (channel = 'telegram'),
 telegram_sender_id BIGINT NOT NULL,
 telegram_chat_id BIGINT NOT NULL,
 telegram_message_id BIGINT NOT NULL,
 body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 4096),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 read_at TIMESTAMPTZ,
 UNIQUE(channel, telegram_chat_id, telegram_message_id)
);
CREATE INDEX IF NOT EXISTS coach_messages_newest_idx ON coach_messages(created_at DESC, message_id DESC);
CREATE INDEX IF NOT EXISTS coach_messages_unread_idx ON coach_messages(created_at DESC) WHERE read_at IS NULL;
