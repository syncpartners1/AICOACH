"""A pasted list of commands must not silently enter the first conversation."""
import asyncio
from unittest.mock import AsyncMock, PropertyMock, patch

from telegram import Update
from telegram.ext import ConversationHandler

from autogpt.coaching.telegram_bot import _build_app


def _update(app, text, commands):
    return Update.de_json({
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1780000000,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Test"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": text.index(command), "length": len(command)}
                         for command in commands],
        },
    }, app.bot)


def test_pasted_commands_rejected_before_conversation():
    app = _build_app("123456789:AAE" + "x" * 32)
    guard = app.handlers[0][0]
    conv = next(h for h in app.handlers[0] if isinstance(h, ConversationHandler))
    assert app.handlers[0].index(guard) < app.handlers[0].index(conv)
    with patch.object(type(app.bot), "username", new_callable=PropertyMock, return_value="testbot"):
        for text, cmds in (("/weekly\n/new_session", ["/weekly", "/new_session"]),
                           ("/weekly\n  /plan", ["/weekly", "/plan"])):
            update = _update(app, text, cmds)
            assert guard.check_update(update)
            assert conv.check_update(update)  # otherwise first command would be dispatched
        for text, cmds in (("/weekly", ["/weekly"]), ("/plan", ["/plan"]),
                           ("/new_session", ["/new_session"]),
                           ("/weekly extra text", ["/weekly"])):
            update = _update(app, text, cmds)
            assert not guard.check_update(update)
            assert conv.check_update(update)


def test_rejection_does_not_mutate_conversation_state():
    from autogpt.coaching.telegram_bot import reject_multi_command
    message = AsyncMock()
    asyncio.run(reject_multi_command(type("Update", (), {"message": message})(), object()))
    message.reply_text.assert_awaited_once()
    assert "one command" in message.reply_text.await_args.args[0]
