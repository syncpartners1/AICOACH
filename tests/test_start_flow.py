"""Start-flow decisions: /start opens a session for linked trainees;
strangers keep the alignment quiz and also get a web-register button."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.ext import ConversationHandler

from autogpt.coaching import telegram_bot
from autogpt.coaching.models import AccountStatus, UserProfile


def _user(status=AccountStatus.ACTIVE, lang="he"):
    return UserProfile(user_id="u1", name="Adi", phone_number="+972500000000",
                       language=lang, account_status=status, telegram_user_id=7)


def _event(text="/start", tg_id=7):
    return SimpleNamespace(message=SimpleNamespace(text=text, reply_text=AsyncMock()),
                           effective_user=SimpleNamespace(id=tg_id, username="adi"))


def _ctx():
    return SimpleNamespace(user_data={})


def test_start_linked_user_opens_session_directly():
    with patch.object(telegram_bot, "_get_linked_user", return_value=_user()), \
         patch.object(telegram_bot, "_get_or_restore_session", return_value=None), \
         patch.object(telegram_bot, "_start_coaching_session", new=AsyncMock()) as begin:
        result = asyncio.run(telegram_bot.start(_event(), _ctx()))
    assert result == telegram_bot.CHATTING
    begin.assert_awaited_once()
    assert begin.call_args.args[2:] == (7, "u1", "Adi", "he")


def test_start_linked_user_with_live_session_rejoins():
    with patch.object(telegram_bot, "_get_linked_user", return_value=_user()), \
         patch.object(telegram_bot, "_get_or_restore_session", return_value=object()), \
         patch.object(telegram_bot, "_start_coaching_session", new=AsyncMock()) as begin:
        event = _event()
        result = asyncio.run(telegram_bot.start(event, _ctx()))
    assert result == telegram_bot.CHATTING
    begin.assert_not_awaited()
    assert event.message.reply_text.call_count == 1  # already_session only


def test_start_pending_user_gets_status_message_not_session():
    with patch.object(telegram_bot, "_get_linked_user",
                      return_value=_user(status=AccountStatus.PENDING)), \
         patch.object(telegram_bot, "_get_or_restore_session", return_value=None), \
         patch.object(telegram_bot, "_start_coaching_session", new=AsyncMock()) as begin:
        result = asyncio.run(telegram_bot.start(_event(), _ctx()))
    assert result == ConversationHandler.END
    begin.assert_not_awaited()


def test_start_stranger_gets_quiz_and_register_button():
    with patch.object(telegram_bot, "_get_linked_user", return_value=None), \
         patch("autogpt.coaching.storage.upsert_funnel_lead"), \
         patch.object(telegram_bot, "_start_coaching_session", new=AsyncMock()) as begin:
        event = _event(tg_id=999)
        result = asyncio.run(telegram_bot.start(event, _ctx()))
    assert result == telegram_bot.FUNNEL_Q1
    begin.assert_not_awaited()
    markup = event.message.reply_text.call_args.kwargs["reply_markup"]
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 2
    assert buttons[0].callback_data == "funnel_start"
    assert buttons[1].url.endswith("/register")
    assert buttons[1].url.startswith("http")
