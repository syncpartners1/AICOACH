import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from autogpt.coaching import telegram_bot as tb, storage
from autogpt.coaching.models import AccountStatus
from tests.test_telegram_identity_security import update

@pytest.mark.parametrize('contact,text,chat', [
    (None,'+972500000000','private'),
    (SimpleNamespace(user_id=99,phone_number='+972500000000'),None,'private'),
    (SimpleNamespace(user_id=None,phone_number='+972500000000'),None,'private'),
    (SimpleNamespace(user_id=42,phone_number='+972500000000'),None,'group'),
    (SimpleNamespace(user_id=42,phone_number='invalid'),None,'private'),
])
def test_registration_rejects_unproven_contact(contact,text,chat):
    with patch.object(storage,'get_user_by_phone') as lookup, patch.object(storage,'register_user_by_phone') as reg, patch.object(storage,'link_telegram') as old, patch.object(storage,'link_telegram_verified_contact') as guard, patch.object(tb,'_start_coaching_session') as start:
        assert asyncio.run(tb.receive_phone(update(contact,text,chat),SimpleNamespace(user_data={}))) == tb.WAITING_PHONE
    lookup.assert_not_called(); reg.assert_not_called(); old.assert_not_called(); guard.assert_not_called(); start.assert_not_called()

@pytest.mark.parametrize('found,ok,status', [(True,True,AccountStatus.ACTIVE),(True,False,AccountStatus.ACTIVE),(True,True,AccountStatus.PENDING),(False,True,AccountStatus.PENDING),(False,False,AccountStatus.PENDING)])
def test_registration_atomic_binding_before_success(found,ok,status):
    user=SimpleNamespace(user_id='u-test',name='Test',language='he',account_status=status)
    u=update(SimpleNamespace(user_id=42,phone_number='972500000000'))
    ctx=SimpleNamespace(user_data={'temp_name':'Test','lang':'he'})
    with patch.object(storage,'get_user_by_phone',return_value=user if found else None), patch.object(storage,'register_user_by_phone',return_value=user) as reg, patch.object(storage,'link_telegram') as old, patch.object(storage,'link_telegram_verified_contact',return_value=ok) as guard, patch.object(tb,'_start_coaching_session',new_callable=AsyncMock) as start, patch.object(tb.coaching_config,'admin_telegram_id',0):
        result=asyncio.run(tb.receive_phone(u,ctx))
    guard.assert_called_once_with('u-test',42,'+972500000000'); old.assert_not_called()
    if found: reg.assert_not_called()
    else: assert reg.call_args.kwargs['account_status'] == AccountStatus.PENDING
    if found and ok and status == AccountStatus.ACTIVE:
        start.assert_awaited_once(); assert result == tb.CHATTING
    else:
        start.assert_not_called(); assert result == tb.ConversationHandler.END
    if not ok:
        assert 'temp_name' in ctx.user_data
        assert u.message.reply_text.await_count == 1


def test_registration_contact_button_and_handler():
    u=update(text='Test')
    asyncio.run(tb.receive_name(u,SimpleNamespace(user_data={'lang':'he'})))
    assert u.message.reply_text.call_args.kwargs['reply_markup'].keyboard[0][0].request_contact
    app=tb._build_app('test-bot-token')
    conversations=[h for hs in app.handlers.values() for h in hs if hasattr(h,'states')]
    assert any('CONTACT' in str(h.filters) for c in conversations for h in c.states.get(tb.WAITING_PHONE,[]))

@pytest.mark.parametrize('found', [True,False])
def test_bridge_conflict_stops_before_email_sync(found):
    from tests.test_bridge import _client,_profile,HEADERS
    user=_profile()
    with patch.object(storage,'get_user_by_telegram',return_value=None), patch.object(storage,'get_user_by_phone',return_value=user if found else None), patch.object(storage,'register_user_by_phone',return_value=user), patch.object(storage,'link_telegram_verified_contact',return_value=False) as guard, patch.object(storage,'link_telegram') as old, patch.object(storage,'_get_client') as db:
        r=_client().post('/internal/telegram/user/ensure',json={'telegram_id':42,'name':'Test','phone':'+972500000000','email':'test@example.invalid'},headers=HEADERS)
    assert r.status_code == 409
    guard.assert_called_once_with('u-1',42,'+972500000000'); old.assert_not_called(); db.assert_not_called()
