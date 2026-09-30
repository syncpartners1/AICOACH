"""Dormant adapters verify identity and replay keys before 3.3 route cutover."""
from unittest.mock import patch
import pytest
from autogpt.coaching import session_adapters as adapters
from autogpt.coaching.models import AccountStatus, UserProfile


def profile(**kw):
    return UserProfile(user_id='u', name='N', phone_number='+972500000001',
                       telegram_user_id=42, **kw)


def test_pwa_actor_uses_profile_not_client_ids():
    assert adapters.pwa_actor(profile()).channel_user_id == 'u'
    with pytest.raises(adapters.InactiveAccount):
        adapters.pwa_actor(profile(account_status=AccountStatus.SUSPENDED))


def test_telegram_unlinked_or_wrong_identity_never_dispatches():
    with pytest.raises(adapters.UnlinkedTelegram):
        adapters.telegram_actor(None, 42)
    with pytest.raises(ValueError, match='does not match'):
        adapters.telegram_actor(profile(), 43)
    assert adapters.telegram_actor(profile(), 42).channel_user_id == '42'


def test_start_profile_must_match_actor():
    actor = adapters.pwa_actor(profile())
    with patch.object(adapters, 'dispatch') as dispatch:
        adapters.start(actor, profile(), objectives=[], past_sessions=[], program=None)
        assert dispatch.call_args.kwargs['client_name'] == 'N'
        dispatch.assert_called_once()
        with pytest.raises(ValueError, match='mismatch'):
            adapters.start(adapters.Actor('other', 'pwa', 'other'), profile(),
                           objectives=[], past_sessions=[], program=None)
        dispatch.assert_called_once()


def test_same_telegram_update_id_for_retry_across_front_doors():
    actor = adapters.telegram_actor(profile(), 42)
    with patch.object(adapters, 'dispatch') as dispatch:
        adapters.message(actor, session_id='s', text='hi', update_id=123)
        adapters.message(actor, session_id='s', text='hi', update_id=123)
    assert [call.kwargs['request_id'] for call in dispatch.call_args_list] == ['tg:123', 'tg:123']
    with pytest.raises(ValueError, match='update ID'):
        adapters.message(actor, session_id='s', text='hi')


def test_pwa_uuid_is_canonical_and_required():
    actor = adapters.pwa_actor(profile())
    with patch.object(adapters, 'dispatch') as dispatch:
        adapters.message(actor, session_id='s', text='hi',
                         client_request_id='550E8400-E29B-41D4-A716-446655440000')
    assert dispatch.call_args.kwargs['request_id'] == 'pwa:550e8400-e29b-41d4-a716-446655440000'
    with pytest.raises(ValueError, match='UUID'):
        adapters.message(actor, session_id='s', text='hi')


def test_cancel_is_separate_from_guided_flow():
    actor = adapters.pwa_actor(profile())
    with patch.object(adapters, 'dispatch') as dispatch:
        adapters.cancel(actor, session_id='s')
    dispatch.assert_called_once_with('cancel', actor, session_id='s')
