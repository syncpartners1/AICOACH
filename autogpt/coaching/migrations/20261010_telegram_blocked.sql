-- Mark a trainee whose Telegram cannot be reached (they blocked the bot, or the chat is gone). Two nullable columns, nothing else changes.
-- Apply in Cloud SQL aicoach_db BEFORE deploying the code that reads and writes them.
-- NULL telegram_blocked_at means reachable. The flag is set from a failed send or from Telegram's "kicked" event and cleared when the user unblocks the bot.
-- Rollback: ALTER TABLE user_profiles DROP COLUMN telegram_blocked_at, DROP COLUMN telegram_blocked_reason; nothing else depends on them.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS telegram_blocked_at timestamptz;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS telegram_blocked_reason text;
