"""M015 primitives never read a stale lease then save outside the CAS boundary."""
from unittest.mock import patch
import pytest
from autogpt.coaching import session_state as s


def test_start_validates_channel_and_conflict_is_not_success():
    with pytest.raises(ValueError):
        s.start(session_id='s', user_id='u', channel='wrong', channel_user_id='i',
                client_id='c', client_name='n', lang='he', system_prompt='', transcript=[])
    with patch.object(s, 'execute_query', return_value=None) as query:
        with pytest.raises(s.SessionBusy):
            s.start(session_id='s', user_id='u', channel='pwa', channel_user_id='i',
                    client_id='c', client_name='n', lang='he', system_prompt='', transcript=[])
    assert 'ON CONFLICT DO NOTHING' in query.call_args.args[0]


def test_append_turn_cas_requires_owner_channel_active_and_version():
    with patch.object(s, 'execute_query', return_value=None) as query:
        assert s.append_turn(session_id='s', user_id='u', channel='telegram', expected_version=7,
                             transcript=[{'role': 'user', 'content': 'hi'}]) is None
    sql, params = query.call_args.args
    assert "status = 'active' AND version = %(version)s" in sql
    assert 'user_id = %(uid)s AND channel = %(channel)s' in sql
    assert params['version'] == 7
    assert query.call_args.kwargs['commit'] is True


def test_stale_claim_is_channel_specific_and_atomic():
    with patch.object(s, 'execute_query', return_value=[{'session_id':'s'}]) as query:
        assert s.claim_stale(channel='pwa', inactivity_minutes=180) == [{'session_id':'s'}]
    sql, params = query.call_args.args
    assert 'FOR UPDATE SKIP LOCKED' in sql
    assert "status = 'finalizing'" in sql
    assert params['channel'] == 'pwa' and params['minutes'] == 180


def test_cancel_claim_is_cas_and_preserves_transcript():
    with patch.object(s, 'execute_query', return_value=None) as query:
        assert s.cancel_claim(session_id='s', expected_version=4, lease_token='00000000-0000-0000-0000-000000000000') is None
    sql = query.call_args.args[0]
    assert 'version = %(version)s AND lease_token = %(token)s::uuid' in sql
    assert 'transcript =' not in sql


def test_reclaim_rotates_token_and_version_in_one_write():
    with patch.object(s, 'execute_query', return_value=[]) as query:
        assert s.reclaim_expired(channel='telegram') == []
    sql = query.call_args.args[0]
    assert 'FOR UPDATE SKIP LOCKED' in sql
    assert 'lease_token = gen_random_uuid()' in sql
    assert 'version = version + 1' in sql


def test_finalizer_is_single_db_function_call_and_not_save_session():
    with patch.object(s, 'execute_query', return_value={'committed': False}) as query:
        assert not s.commit_finalization(session_id='s', expected_version=2, lease_token='token',
                                         summary={'session_id': 's'}, key_results=[], obstacles=[])
    assert 'finalize_claimed_coaching_session' in query.call_args.args[0]
    assert query.call_args.kwargs['commit'] is True


def test_migration_locks_claim_and_publishes_in_transaction():
    from pathlib import Path
    schema = (Path(__file__).parent.parent / 'autogpt/coaching/supabase_schema.sql').read_text()
    fn = schema.split('CREATE OR REPLACE FUNCTION finalize_claimed_coaching_session', 1)[1]
    assert 'FOR UPDATE' in fn
    assert "claimed.status <> 'finalizing'" in fn
    assert 'claimed.version <> p_version' in fn
    assert 'claimed.lease_token IS DISTINCT FROM p_lease_token' in fn
    assert 'INSERT INTO coaching_sessions' in fn
    assert "SET status = 'completed'" in fn
