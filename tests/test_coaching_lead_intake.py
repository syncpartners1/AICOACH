"""Regression tests for durable coaching questionnaire intake and ClickUp uncertainty."""
import asyncio
from unittest.mock import patch
from uuid import uuid4

from autogpt.coaching.wix_qualify import (
    CoachingQualPayload, _process_coaching_qualify_background,
    handle_coaching_qualify, save_coaching_submission,
)


def _payload(submission_id=None):
    return CoachingQualPayload(
        submission_id=submission_id or uuid4(), q1_challenge='A challenge',
        q2_outcome='A goal', q3_priority='yes', q4_commit_time='yes',
        q5_commit_tasks='yes', q6_coaching='yes', q7_capability='yes',
        q8_name='Example Person', q9_email='person@example.test', q10_source='site',
    )


def test_answers_saved_before_clickup_is_queued():
    payload = _payload()
    class Queue:
        def add_task(self, *args):
            assert calls == ['saved']
            calls.append('queued')
    calls = []
    with patch('autogpt.coaching.wix_qualify.save_coaching_submission', side_effect=lambda *args: (calls.append('saved') or str(payload.submission_id), True)):
        response = asyncio.run(handle_coaching_qualify(payload, Queue()))
    assert calls == ['saved', 'queued']
    assert response['submission_id'] == str(payload.submission_id)


def test_repeat_submission_does_not_queue_or_send():
    class Queue:
        def add_task(self, *args):
            raise AssertionError('duplicate must not send')
    payload = _payload()
    with patch('autogpt.coaching.wix_qualify.save_coaching_submission', return_value=(str(payload.submission_id), False)):
        response = asyncio.run(handle_coaching_qualify(payload, Queue()))
    assert response['clickup'] == 'previously_received'


def test_saved_record_contains_answers_and_unique_id():
    payload = _payload()
    with patch('autogpt.coaching.db.execute_query', return_value={'submission_id': str(payload.submission_id)}) as db:
        id_, created = save_coaching_submission(payload, 'PASS')
    assert created and id_ == str(payload.submission_id)
    query, params = db.call_args.args
    assert 'ON CONFLICT (submission_id) DO NOTHING' in query
    assert 'A challenge' in params['answers']
    assert 'q7_capability' in params['answers']


def test_clickup_uncertain_outcome_needs_manual_review_and_no_retry():
    payload = _payload()
    with patch('autogpt.coaching.wix_qualify.create_clickup_task', return_value=None) as clickup, \
         patch('autogpt.coaching.wix_qualify._record_clickup_result') as record, \
         patch('autogpt.coaching.wix_qualify.notify_clickup_failure') as alert, \
         patch('autogpt.coaching.gmail_service.send_qualify_notification'), \
         patch('autogpt.coaching.gmail_service.send_lead_response'):
        _process_coaching_qualify_background(payload, 'PASS', str(payload.submission_id))
    clickup.assert_called_once()
    record.assert_called_once_with(str(payload.submission_id), None)
    alert.assert_called_once_with(str(payload.submission_id))


def test_db_failure_does_not_queue_clickup():
    class Queue:
        def add_task(self, *args):
            raise AssertionError('must not send without saved answers')
    with patch('autogpt.coaching.wix_qualify.save_coaching_submission', side_effect=RuntimeError('database unavailable')):
        try:
            asyncio.run(handle_coaching_qualify(_payload(), Queue()))
        except RuntimeError:
            pass
        else:
            raise AssertionError('database error must fail the request')


def test_clickup_result_updates_state_without_automatic_retry():
    from autogpt.coaching.wix_qualify import _record_clickup_result
    with patch('autogpt.coaching.db.execute_query') as db:
        _record_clickup_result('abc', None)
    assert db.call_args.args[1]['state'] == 'needs_review'
    with patch('autogpt.coaching.db.execute_query') as db:
        _record_clickup_result('abc', 'https://app.clickup.com/t/1234')
    assert db.call_args.args[1]['state'] == 'created'
    assert db.call_args.args[1]['task_id'] == '1234'


def test_failure_alert_sends_only_opaque_id_to_existing_admin_bot():
    from autogpt.coaching.wix_qualify import notify_clickup_failure
    from unittest.mock import Mock
    with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test-only-token',
                                    'ADMIN_TELEGRAM_ID': '123'}), \
         patch('autogpt.coaching.wix_qualify.requests.post',
               return_value=Mock(json=lambda: {'ok': True})) as post:
        assert notify_clickup_failure('test-submission-id')
    kwargs = post.call_args.kwargs
    assert kwargs['json']['chat_id'] == '123'
    assert 'test-submission-id' in kwargs['json']['text']
    assert 'person@example.test' not in kwargs['json']['text']
    assert kwargs['timeout'] == 10


def test_alert_failure_is_reported_and_does_not_raise():
    from autogpt.coaching.wix_qualify import notify_clickup_failure
    with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test-only-token',
                                    'ADMIN_TELEGRAM_ID': '123'}), \
         patch('autogpt.coaching.wix_qualify.requests.post', side_effect=TimeoutError):
        assert not notify_clickup_failure('test-submission-id')


def test_alert_missing_configuration_is_not_reported_as_delivered():
    from autogpt.coaching.wix_qualify import notify_clickup_failure
    with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': '', 'ADMIN_TELEGRAM_ID': ''}), \
         patch('autogpt.coaching.wix_qualify.requests.post') as post:
        assert not notify_clickup_failure('test-submission-id')
    post.assert_not_called()
