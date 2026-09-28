"""Free text after a bot redeploy resumes a persisted session, not a new flow."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

from telegram import Update

from autogpt.coaching import telegram_bot as tb


def _update(app, text, *, reply_to=False):
    payload = {
        'update_id': 789,
        'message': {
            'message_id': 789, 'date': 1780000000,
            'chat': {'id': 42, 'type': 'private'},
            'from': {'id': 42, 'is_bot': False, 'first_name': 'Test'},
            'text': text,
        },
    }
    if text.startswith('/'):
        payload['message']['entities'] = [{'type': 'bot_command', 'offset': 0, 'length': len(text.split()[0])}]
    if reply_to:
        payload['message']['reply_to_message'] = {
            'message_id': 2, 'date': 1780000000,
            'chat': {'id': 42, 'type': 'private'},
            'from': {'id': 999, 'is_bot': True, 'first_name': 'Bot'},
            'text': 'prior',
        }
    return Update.de_json(payload, app.bot)


def test_fallback_is_after_conversation_and_admin_reply_and_excludes_commands():
    app = tb._build_app('123456789:AAE' + 'x' * 32)
    handlers = app.handlers[0]
    conv = next(h for h in handlers if h.__class__.__name__ == 'ConversationHandler')
    admin = next(h for h in handlers if getattr(h, 'callback', None) is tb.admin_reply_handler)
    fallback = next(h for h in handlers if getattr(h, 'callback', None) is tb.restore_chat_after_restart)
    assert handlers.index(conv) < handlers.index(admin) < handlers.index(fallback)
    with patch.object(type(app.bot), 'username', new_callable=PropertyMock, return_value='testbot'):
        assert fallback.check_update(_update(app, 'hello'))
        assert not fallback.check_update(_update(app, '/start'))
        assert admin.check_update(_update(app, 'reply', reply_to=True))


def test_restores_only_existing_telegram_session_and_uses_normal_chat_handler():
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42))
    with patch.object(tb, '_get_or_restore_session', return_value=object()) as restore, \
         patch.object(tb, 'handle_message', new_callable=AsyncMock) as chat:
        asyncio.run(tb.restore_chat_after_restart(update, object()))
        restore.assert_called_once_with(42)
        chat.assert_awaited_once()
    with patch.object(tb, '_get_or_restore_session', return_value=None), \
         patch.object(tb, 'handle_message', new_callable=AsyncMock) as chat:
        asyncio.run(tb.restore_chat_after_restart(update, object()))
        chat.assert_not_awaited()
