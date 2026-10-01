import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching import coach_inbox as inbox
from autogpt.coaching import telegram_bot as bot

MID = '10000000-0000-0000-0000-000000000001'
UID = '20000000-0000-0000-0000-000000000002'


def row(**overrides):
    data = dict(message_id=MID, user_id=UID, sender_name='שם <script>', channel='telegram',
                body='<img src=x onerror=alert(1)>\nשלום',
                created_at=datetime(2026, 10, 1, tzinfo=timezone.utc), read_at=None)
    data.update(overrides)
    return data


def source():
    return dict(user_id=UID, sender_name='Trainee', sender_id=12, chat_id=13,
                source_message_id=14, body='  hello  ')


@contextmanager
def cursor_mock(cur, events=None, commit=False):
    yield cur
    if events is not None:
        events.append('commit' if commit else 'read')


def test_save_commits_before_return_and_uses_source_key():
    cur = MagicMock(); cur.fetchone.return_value = {'message_id': MID}
    events = []
    with patch.object(inbox, 'get_db_cursor', side_effect=lambda **kw: cursor_mock(cur, events, **kw)):
        assert inbox.save_message(**source()) == MID
        assert events == ['commit']
    sql, params = cur.execute.call_args.args
    assert 'ON CONFLICT (channel,telegram_chat_id,telegram_message_id) DO NOTHING' in sql
    assert params[-1] == 'hello'
    assert params[3:6] == (12, 13, 14)


def test_retry_returns_original_id_and_does_not_overwrite():
    cur = MagicMock(); cur.fetchone.side_effect = [None, dict(message_id=MID, user_id=UID, telegram_sender_id=12, body='hello')]
    with patch.object(inbox, 'get_db_cursor', side_effect=lambda **kw: cursor_mock(cur, **kw)):
        assert inbox.save_message(**source()) == MID
    assert cur.execute.call_count == 2


def test_retry_identity_conflict_fails():
    cur = MagicMock(); cur.fetchone.side_effect = [None, dict(message_id=MID, user_id='other', telegram_sender_id=12, body='hello')]
    with patch.object(inbox, 'get_db_cursor', side_effect=lambda **kw: cursor_mock(cur, **kw)):
        with pytest.raises(ValueError): inbox.save_message(**source())


@pytest.mark.parametrize('body', ['', ' ', 'x'*4097])
def test_invalid_body_never_reaches_db(body):
    with patch.object(inbox, 'get_db_cursor') as db:
        with pytest.raises(ValueError): inbox.save_message(**{**source(), 'body': body})
        db.assert_not_called()


def test_database_error_propagates():
    with patch.object(inbox, 'get_db_cursor', side_effect=RuntimeError('migration absent')):
        with pytest.raises(RuntimeError): inbox.save_message(**source())


def test_unread_count():
    cur = MagicMock(); cur.fetchone.return_value = {'count': 4}
    with patch.object(inbox, 'get_db_cursor', side_effect=lambda **kw: cursor_mock(cur, **kw)):
        assert inbox.unread_count() == 4
    assert 'read_at IS NULL' in cur.execute.call_args.args[0]


def test_page_is_bounded_and_stably_ordered():
    cur = MagicMock(); cur.fetchall.return_value = [row()] * 31
    with patch.object(inbox, 'get_db_cursor', side_effect=lambda **kw: cursor_mock(cur, **kw)):
        rows, more = inbox.list_messages(2)
    assert len(rows) == 30 and more
    assert cur.execute.call_args.args[1] == (31, 30)
    assert 'ORDER BY created_at DESC,message_id DESC' in cur.execute.call_args.args[0]


@pytest.mark.parametrize('page', [0, 10001])
def test_bad_page(page):
    with pytest.raises(ValueError): inbox.list_messages(page)


def test_mark_read_commits_and_preserves_timestamp():
    cur = MagicMock(); cur.fetchone.return_value = {'message_id': MID}
    events = []
    with patch.object(inbox, 'get_db_cursor', side_effect=lambda **kw: cursor_mock(cur, events, **kw)):
        assert inbox.mark_read(MID)
    assert events == ['commit']
    assert 'COALESCE(read_at,now())' in cur.execute.call_args.args[0]


def test_mark_missing_returns_false():
    cur = MagicMock(); cur.fetchone.return_value = None
    with patch.object(inbox, 'get_db_cursor', side_effect=lambda **kw: cursor_mock(cur, **kw)):
        assert not inbox.mark_read(MID)


def test_ui_escapes_content_and_has_read_action_and_paging():
    html = inbox.render_inbox([row()], 1, page=2, has_next=True)
    assert '<script>' not in html.split('<div class="body">')[1].split('</div>')[0]
    assert '&lt;img' in html and '&lt;script&gt;' in html
    assert 'dir="rtl"' in html and '?page=1' in html and '?page=3' in html
    assert 'data-message-id="'+MID+'"' in html
    assert '01/10/2026 03:00' in html


def test_ui_error_is_not_empty_inbox():
    html = inbox.render_inbox([], 0, error=True)
    assert 'אין להסיק שאין הודעות' in html
    assert 'אין הודעות בתיבה.' not in html


def update():
    return SimpleNamespace(effective_user=SimpleNamespace(id=12), effective_chat=SimpleNamespace(id=13),
       message=SimpleNamespace(text='hello', message_id=14, reply_text=AsyncMock()))


def context():
    return SimpleNamespace(user_data={'lang':'he'}, bot=SimpleNamespace(send_message=AsyncMock()))


def test_handler_saves_then_acknowledges_without_telegram_forward():
    u, c = update(), context(); events=[]
    def save(**kw): events.append('saved'); return MID
    async def reply(text, **kw): events.append(text)
    u.message.reply_text.side_effect = reply
    with patch.object(bot, '_get_linked_user', return_value=SimpleNamespace(user_id=UID,name='Trainee')), patch.object(inbox,'save_message',side_effect=save):
        assert asyncio.run(bot.msg_receive(u,c)) == bot.ConversationHandler.END
    assert events[0] == 'saved' and 'נשמרה' in events[1]
    c.bot.send_message.assert_not_called()


def test_handler_storage_failure_no_success_and_allows_retry():
    u,c=update(),context()
    with patch.object(bot,'_get_linked_user',return_value=SimpleNamespace(user_id=UID,name='Trainee')), patch.object(inbox,'save_message',side_effect=RuntimeError('migration missing')):
        assert asyncio.run(bot.msg_receive(u,c)) == bot.MSG_WAITING
    assert 'לא נשמרה' in u.message.reply_text.call_args.args[0]
    c.bot.send_message.assert_not_called()


def test_start_no_longer_needs_admin_telegram_id():
    u,c=update(),context()
    with patch.object(bot,'_get_linked_user',return_value=SimpleNamespace(user_id=UID,name='Trainee',language='he')), patch.object(bot.coaching_config,'admin_telegram_id',0):
        assert asyncio.run(bot.msg_start(u,c)) == bot.MSG_WAITING


def test_unlinked_receipt_is_not_saved():
    u,c=update(),context()
    with patch.object(bot,'_get_linked_user',return_value=None), patch.object(inbox,'save_message') as save:
        assert asyncio.run(bot.msg_receive(u,c)) == bot.ConversationHandler.END
    save.assert_not_called()


def test_ack_failure_does_not_report_storage_failure():
    u,c=update(),context();u.message.reply_text.side_effect=RuntimeError('telegram unavailable')
    with patch.object(bot,'_get_linked_user',return_value=SimpleNamespace(user_id=UID,name='Trainee')), patch.object(inbox,'save_message',return_value=MID):
        with pytest.raises(RuntimeError): asyncio.run(bot.msg_receive(u,c))
    assert u.message.reply_text.call_count == 1


def test_admin_routes_auth_error_mark_read_and_csrf():
    from autogpt.coaching import api
    client=TestClient(api.app)
    with patch.object(api,'_is_admin_authenticated',return_value=False):
        assert client.get('/admin/messages').status_code == 401
        assert client.post(f'/admin/messages/{MID}/read').status_code == 403
    with patch.object(api,'_is_admin_authenticated',return_value=True), patch.object(inbox,'list_messages',return_value=([row()],False)), patch.object(inbox,'unread_count',return_value=1):
        assert client.get('/admin/messages').status_code == 200
        assert client.get('/admin/messages?page=0').status_code == 422
        with patch.object(inbox,'mark_read',return_value=True) as mark:
            assert client.post(f'/admin/messages/{MID}/read',headers={'X-Inbox-Action':'mark-read','Origin':'https://evil.invalid'}).status_code == 403
            mark.assert_not_called()
            assert client.post(f'/admin/messages/{MID}/read',headers={'X-Inbox-Action':'mark-read','Origin':'http://testserver'}).status_code == 200
        with patch.object(inbox,'mark_read',return_value=False):
            assert client.post(f'/admin/messages/{MID}/read',headers={'X-Inbox-Action':'mark-read','Origin':'http://testserver'}).status_code == 404
        with patch.object(inbox,'list_messages',side_effect=RuntimeError('missing table')):
            res=client.get('/admin/messages'); assert res.status_code == 503 and 'אין להסיק' in res.text


def test_dashboard_link_displays_count_or_error():
    from autogpt.coaching.admin_ui import render_admin
    assert '7 לא נקראו' in render_admin([], [], inbox_unread=7)
    assert 'מונה לא זמין' in render_admin([], [])
