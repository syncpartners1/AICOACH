import asyncio
import hashlib
import hmac
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching import telegram_auth as ta
from autogpt.coaching import telegram_bot as tb
from autogpt.coaching import storage
from autogpt.coaching.config import coaching_config

TOKEN = 'test-bot-token'
NOW = 1790855000

def signed(**updates):
    data = {'id': 42, 'first_name': 'Test', 'auth_date': NOW}
    data.update(updates)
    text = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()) if v is not None)
    data['hash'] = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), text.encode(), hashlib.sha256).hexdigest()
    return data

@pytest.mark.parametrize('age', [0, 30, 600])
def test_fresh_widget_proof(age):
    with patch('time.time', return_value=NOW):
        assert ta.verify_telegram_auth(signed(auth_date=NOW-age), TOKEN)

@pytest.mark.parametrize('data', [
    {'id': 42}, signed(auth_date=NOW-601), signed(auth_date=NOW+1),
    signed(auth_date='bad'), signed(auth_date=None), signed(id=0), signed(id='bad'),
    {**signed(), 'hash': 'bad'}, {**signed(), 'hash': []},
])
def test_invalid_widget_proof(data):
    with patch('time.time', return_value=NOW):
        assert not ta.verify_telegram_auth(data, TOKEN)

@pytest.mark.parametrize('payload', [{'id': 42}, signed(auth_date=NOW-601), signed(auth_date=NOW+1), {**signed(), 'hash': 'bad'}])
def test_public_login_rejects_without_storage_or_cookie(payload):
    from autogpt.coaching.api import app
    with patch.object(coaching_config, 'telegram_bot_token', TOKEN), patch('time.time', return_value=NOW), patch.object(storage, 'telegram_oauth') as lookup:
        response = TestClient(app).post('/auth/telegram', json=payload)
    assert response.status_code == 401
    assert 'set-cookie' not in response.headers
    lookup.assert_not_called()

def test_public_valid_widget_login():
    from autogpt.coaching.api import app
    from autogpt.coaching.models import UserProfile
    user = UserProfile(user_id='u-test', name='Test', phone_number='+972500000000')
    with patch.object(coaching_config, 'telegram_bot_token', TOKEN), patch('time.time', return_value=NOW), patch.object(storage, 'telegram_oauth', return_value=user) as lookup:
        response = TestClient(app).post('/auth/telegram', json=signed())
    assert response.status_code == 200
    assert 'set-cookie' in response.headers
    lookup.assert_called_once()

def update(contact=None, text=None, chat='private'):
    return SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(type=chat), message=SimpleNamespace(contact=contact, text=text, reply_text=AsyncMock()))

@pytest.mark.parametrize('contact,text,chat', [
    (None, '+972500000000', 'private'),
    (SimpleNamespace(user_id=99, phone_number='+972500000000'), None, 'private'),
    (SimpleNamespace(user_id=None, phone_number='+972500000000'), None, 'private'),
    (SimpleNamespace(user_id=42, phone_number='+972500000000'), None, 'group'),
    (SimpleNamespace(user_id=42, phone_number='invalid'), None, 'private'),
])
def test_link_rejects_non_self_contact(contact, text, chat):
    with patch.object(storage, 'get_user_by_phone') as lookup, patch.object(storage, 'link_telegram') as old_link, patch.object(storage, 'link_telegram_verified_contact', create=True) as link:
        asyncio.run(tb.link_receive_phone(update(contact, text, chat), SimpleNamespace(user_data={})))
    lookup.assert_not_called(); link.assert_not_called(); old_link.assert_not_called()

@pytest.mark.parametrize('ok', [True, False])
def test_self_contact_uses_atomic_guard(ok):
    user = SimpleNamespace(user_id='u-test', name='Test', language='he')
    u = update(SimpleNamespace(user_id=42, phone_number='972500000000'))
    with patch.object(storage, 'get_user_by_phone', return_value=user) as lookup, patch.object(storage, 'link_telegram_verified_contact', return_value=ok) as link, patch.object(storage, 'link_telegram') as old_link:
        asyncio.run(tb.link_receive_phone(u, SimpleNamespace(user_data={})))
    lookup.assert_called_once_with('+972500000000')
    link.assert_called_once_with('u-test', 42, '+972500000000')
    old_link.assert_not_called()
    if ok:
        assert u.message.reply_text.call_args.kwargs.get('reply_markup') is not None

def test_link_start_uses_own_contact_button():
    u = update(text='/link')
    with patch.object(tb, '_get_linked_user', return_value=None):
        asyncio.run(tb.link_start(u, SimpleNamespace(user_data={})))
    keyboard = u.message.reply_text.call_args.kwargs['reply_markup']
    assert keyboard.keyboard[0][0].request_contact is True

@pytest.mark.parametrize('found', [True, False])
def test_atomic_phone_and_binding_guard(found):
    cur = MagicMock(); cur.fetchone.return_value = {'user_id': 'u-test'} if found else None
    @contextmanager
    def cursor(**kw):
        assert kw == {'commit': True}
        yield cur
    with patch('autogpt.coaching.db.get_db_cursor', side_effect=cursor):
        assert storage.link_telegram_verified_contact('u-test',42,'+972500000000') is found
    sql, values = cur.execute.call_args.args
    assert 'phone_number=%s' in sql and 'telegram_user_id IS NULL OR telegram_user_id=%s' in sql
    assert values == (42,'u-test','+972500000000',42)

def test_binding_conflict_fails_closed():
    from psycopg2.errors import UniqueViolation
    @contextmanager
    def cursor(**kw):
        raise UniqueViolation()
        yield
    with patch('autogpt.coaching.db.get_db_cursor', side_effect=cursor):
        assert storage.link_telegram_verified_contact('u-test',42,'+972500000000') is False

def test_link_contact_handler_registered():
    from telegram.ext import MessageHandler
    app = tb._build_app(TOKEN)
    conversations = [h for handlers in app.handlers.values() for h in handlers if hasattr(h,'states')]
    handlers = [h for c in conversations for h in c.states.get(tb.LINK_WAITING_PHONE, [])]
    assert any(isinstance(h,MessageHandler) and 'CONTACT' in str(h.filters) for h in handlers)
