"""A short coaching session must preserve its transcript rather than invent a summary."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from autogpt.coaching import telegram_bot as tb
from autogpt.coaching.models import AlertLevel
from autogpt.coaching.session import CoachingSession


def short_session():
    return CoachingSession.restore({
        "session_id": "brief-1", "client_id": "telegram_42", "client_name": "Test",
        "user_id": "test-user", "lang": "he", "system_prompt": "coach",
        "message_history": [{"role": "assistant", "content": "Hello"},
                            {"role": "user", "content": "Hi"}],
    })


def test_brief_summary_has_full_transcript_and_no_invented_log():
    session = short_session()
    summary = session.brief_summary()
    assert summary.session_id == "brief-1"
    assert summary.raw_conversation == session.full_message_history
    assert summary.alerts.level == AlertLevel.YELLOW
    assert not summary.weekly_log.focus_goal


def test_timer_saves_brief_session_without_model():
    session = short_session()
    bot = SimpleNamespace(send_chat_action=AsyncMock())
    tb._sessions[42] = session
    try:
        with patch("autogpt.coaching.storage.save_session") as save, \
             patch("autogpt.coaching.storage.delete_telegram_session") as delete, \
             patch.object(session, "extract_summary", side_effect=AssertionError("LLM called")):
            asyncio.run(tb._auto_finalize_session(bot, 42, 42, "he"))
        save.assert_called_once()
        assert save.call_args.args[0].raw_conversation == session.full_message_history
        delete.assert_called_once_with(42)
    finally:
        tb._sessions.pop(42, None)


def test_four_messages_still_extracts():
    session = short_session()
    session.full_message_history.extend([{"role": "user", "content": "more"},
                                         {"role": "assistant", "content": "reply"}])
    session.extract_summary = Mock(return_value=session.brief_summary())
    bot = SimpleNamespace(send_chat_action=AsyncMock())
    tb._sessions[42] = session
    try:
        with patch("autogpt.coaching.storage.save_session"), \
             patch("autogpt.coaching.storage.delete_telegram_session"):
            asyncio.run(tb._auto_finalize_session(bot, 42, 42, "he"))
        session.extract_summary.assert_called_once()
    finally:
        tb._sessions.pop(42, None)
