"""A trainee who blocks the bot is flagged once, the coach is told once, and the email still goes."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest, Forbidden, NetworkError

from autogpt.coaching import telegram_reachability as tr

MIG = Path("autogpt/coaching/migrations/20261010_telegram_blocked.sql")


def run(coro):
    return asyncio.run(coro)


def test_migration_adds_two_nullable_columns_only():
    body = " ".join(l for l in MIG.read_text().splitlines() if not l.strip().startswith("--"))
    stmts = [s.strip() for s in body.split(";") if s.strip()]
    assert stmts == ["ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS telegram_blocked_at timestamptz",
                     "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS telegram_blocked_reason text"]


@pytest.mark.parametrize("exc,expected", [
    (Forbidden("Forbidden: bot was blocked by the user"), "bot was blocked by the user"),
    (Forbidden("Forbidden: user is deactivated"), "user is deactivated"),
    (BadRequest("Chat not found"), "chat not found"),
    (BadRequest("Can't parse entities"), None),
    (NetworkError("timeout"), None),
    (RuntimeError("boom"), None),
])
def test_only_real_unreachable_errors_are_classified(exc, expected):
    assert tr.unreachable_reason(exc) == expected


def test_first_failure_flags_and_alerts_the_coach_once():
    bot = SimpleNamespace(send_message=AsyncMock())
    with patch.object(tr, "mark_blocked", side_effect=[{"user_id": "u", "name": "Iz<zy>", "email": "i@x.co",
                                                       "language": "he"}, None]), \
         patch.object(tr.coaching_config, "admin_telegram_id", 999):
        assert run(tr.record_unreachable(bot, 5, "bot was blocked by the user")) is True
        assert run(tr.record_unreachable(bot, 5, "bot was blocked by the user")) is False
    assert bot.send_message.await_count == 1
    sent = bot.send_message.await_args.kwargs
    assert sent["chat_id"] == 999 and "Iz&lt;zy&gt;" in sent["text"] and "by email" in sent["text"]


def test_a_failing_database_never_breaks_the_caller():
    bot = SimpleNamespace(send_message=AsyncMock())
    with patch.object(tr, "mark_blocked", side_effect=RuntimeError("no column")):
        assert run(tr.record_unreachable(bot, 5, "x")) is False
    bot.send_message.assert_not_awaited()


def test_flag_lookup_never_raises():
    with patch("autogpt.coaching.db.execute_query", side_effect=RuntimeError("column does not exist")):
        assert tr.blocked_telegram_ids() == set()
    with patch("autogpt.coaching.db.execute_query", return_value=[{"telegram_user_id": 7}]):
        assert tr.blocked_telegram_ids() == {7}


def test_sql_sets_only_when_unset_and_clears_only_when_set():
    with patch("autogpt.coaching.db.execute_query", return_value=None) as q:
        tr.mark_blocked(5, "r")
        assert "telegram_blocked_at IS NULL" in q.call_args.args[0] and "RETURNING" in q.call_args.args[0]
        tr.clear_blocked(5)
        assert "telegram_blocked_at IS NOT NULL" in q.call_args.args[0]


def _event(status, chat_type="private"):
    return SimpleNamespace(my_chat_member=SimpleNamespace(chat=SimpleNamespace(type=chat_type, id=5),
                                                          new_chat_member=SimpleNamespace(status=status)))


def test_kicked_event_flags_and_member_event_clears_and_groups_are_ignored():
    ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    with patch.object(tr, "record_unreachable", new=AsyncMock()) as rec, patch.object(tr, "clear_blocked") as clr:
        run(tr.on_my_chat_member(_event("kicked"), ctx))
        rec.assert_awaited_once()
        run(tr.on_my_chat_member(_event("member"), ctx))
        clr.assert_called_once_with(5)
        run(tr.on_my_chat_member(_event("kicked", "group"), ctx))
        assert rec.await_count == 1


def test_handler_is_registered_with_the_bot():
    from autogpt.coaching import telegram_bot
    from telegram.ext import ChatMemberHandler
    app = telegram_bot._build_app("123456:TEST")
    assert any(isinstance(h, ChatMemberHandler) for group in app.handlers.values() for h in group)


def _broadcast(rows, send, blocked=frozenset()):
    from autogpt.coaching import telegram_bot as tb
    db = MagicMock()
    db.table.return_value.select.return_value.not_.is_.return_value.execute.return_value.data = rows
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=SimpleNamespace(reply_text=AsyncMock()))
    ctx = SimpleNamespace(args=["hello"], bot=SimpleNamespace(send_message=send))
    with patch.object(tb, "_is_admin", return_value=True), patch("autogpt.coaching.storage._get_client", return_value=db), \
         patch.object(tr, "blocked_telegram_ids", return_value=set(blocked)), \
         patch.object(tr, "record_unreachable", new=AsyncMock()) as rec, \
         patch("autogpt.coaching.notifications.notify_email_leg", return_value=True) as mail:
        run(tb.admin_broadcast(update, ctx))
    return update.message.reply_text.await_args.args[0], rec, mail


ROWS = [{"telegram_user_id": 1, "name": "A", "language": "en", "email": "a@x.co"},
        {"telegram_user_id": 2, "name": "B", "language": "he", "email": "b@x.co"}]


def test_broadcast_emails_a_blocked_user_and_flags_them():
    async def send(chat_id, text, parse_mode):
        if chat_id == 2:
            raise Forbidden("Forbidden: bot was blocked by the user")
    out, rec, mail = _broadcast(ROWS, send)
    assert mail.call_count == 2 and rec.await_count == 1
    assert "1 user(s), 2 email(s), 1 not reachable" in out


def test_broadcast_skips_the_telegram_send_for_a_known_blocked_user_but_still_emails():
    send = AsyncMock()
    out, rec, mail = _broadcast(ROWS, send, blocked={2})
    assert send.await_count == 1 and mail.call_count == 2 and rec.await_count == 0
    assert "1 not reachable" in out


def test_a_temporary_error_is_not_treated_as_blocked():
    async def send(chat_id, text, parse_mode):
        raise NetworkError("timeout")
    out, rec, mail = _broadcast(ROWS, send)
    assert rec.await_count == 0 and "not reachable" not in out
