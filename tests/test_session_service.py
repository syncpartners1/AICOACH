"""Channel and retry guarantees for the dormant shared session service."""
from contextlib import contextmanager
from unittest.mock import Mock, patch
import hashlib
import pytest
from autogpt.coaching import session_service as svc


ROW = {'session_id': 's', 'user_id': 'u', 'channel': 'telegram',
       'channel_user_id': '42', 'status': 'active', 'version': 2,
       'transcript': [], 'client_id': 'c', 'client_name': 'N',
       'lang': 'he', 'system_prompt': 'coach'}


def test_other_channel_cannot_resume_or_cancel():
    with patch.object(svc.state, 'find_active', return_value=ROW), \
         patch.object(svc.state, 'cancel_active') as cancel:
        with pytest.raises(svc.ChannelMismatch) as err:
            svc.cancel(user_id='u', channel='pwa', channel_user_id='u', session_id='s')
        assert err.value.active_channel == 'telegram'
        cancel.assert_not_called()


def test_same_channel_wrong_identity_cannot_resume():
    with patch.object(svc.state, 'find_active', return_value=ROW):
        with pytest.raises(svc.ChannelMismatch):
            svc.resume(user_id='u', channel='telegram', channel_user_id='99')


def test_racing_start_rechecks_channel_before_resuming():
    with patch.object(svc.state, 'find_active', side_effect=[None, ROW]), \
         patch.object(svc.state, 'start', side_effect=svc.state.SessionBusy), \
         patch.object(svc, 'CoachingSession') as session:
        session.return_value.session_id = 'new'
        session.return_value.full_message_history = []
        session.return_value.lang = 'he'
        session.return_value._system_prompt = 'coach'
        with pytest.raises(svc.ChannelMismatch):
            svc.start(user_id='u', channel='pwa', channel_user_id='u',
                      client_id='c', client_name='N')


def test_replayed_request_returns_cached_reply_without_model_call():
    cursor = Mock()
    cursor.fetchone.side_effect = [ROW, {'reply': 'cached', 'request_sha256': hashlib.sha256(b'hi').hexdigest()}]
    @contextmanager
    def db(commit):
        assert commit
        yield cursor
    with patch.object(svc, 'get_db_cursor', db), patch.object(svc, '_restore') as restore:
        assert svc.message(user_id='u', channel='telegram', channel_user_id='42',
                           session_id='s', request_id='tg-update-1', text='hi') == 'cached'
    restore.assert_not_called()
    assert cursor.execute.call_count == 2
    assert 'FOR UPDATE' in cursor.execute.call_args_list[0].args[0]


def test_request_id_reuse_with_different_text_rejected():
    cursor = Mock()
    cursor.fetchone.side_effect = [ROW, {'reply': 'old', 'request_sha256': hashlib.sha256(b'old').hexdigest()}]
    @contextmanager
    def db(commit):
        yield cursor
    with patch.object(svc, 'get_db_cursor', db):
        with pytest.raises(ValueError, match='Request ID reused'):
            svc.message(user_id='u', channel='telegram', channel_user_id='42',
                        session_id='s', request_id='same', text='different')
    assert cursor.execute.call_count == 2


def test_end_claims_before_model_and_cancels_claim_on_failure():
    claimed = dict(ROW, status='finalizing', lease_token='t')
    with patch.object(svc, 'resume', return_value=ROW), \
         patch.object(svc.state, 'claim_one', return_value=claimed), \
         patch.object(svc.state, 'cancel_claim') as undo, \
         patch.object(svc, '_restore', side_effect=RuntimeError('model failed')):
        with pytest.raises(RuntimeError):
            svc.end(user_id='u', channel='telegram', channel_user_id='42', session_id='s')
    undo.assert_called_once_with(session_id='s', expected_version=2, lease_token='t')
